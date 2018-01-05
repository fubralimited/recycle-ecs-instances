# recycle-ecs-instances
#
# Recreates all instances in an ECS cluster that is managed with an auto scaling
# group. It does this without any downtime to any running services.
#
# This is performed by temporarily increasing the desired capacity (and max
# capacity if required) of the auto scaling group. By doing this we get an extra
# instance in the ECS cluster and can proceed to iterate all instances that
# already existed, draining and then terminating them.
#
# Assumptions:
#  - Never more than 100 container instances in an ECS cluster due to paging
#    being ignored.
#
# Author: Ollie Armstrong <ollie@fubra.com>

import boto3
import argparse
from time import sleep

SUSPEND_PROCESSES = ['ReplaceUnhealthy', 'AlarmNotification', 'ScheduledActions', 'AZRebalance']
POLL_INTERVAL = 15

# Argument parsing
parser = argparse.ArgumentParser(description='Recreates all ECS container instances.')
parser.add_argument('--asg-name', required=True, help='The name of the autoscaling group.')
parser.add_argument('--ecs-cluster', required=True, help='The name of the ECS cluster.')
parser.add_argument('--aws-region', required=True, help='The name of the AWS region (e.g. eu-west-1).')
args = vars(parser.parse_args())
ASG_NAME = args['asg_name']
ECS_CLUSTER = args['ecs_cluster']
AWS_REGION = args['aws_region']

# Boto clients
ecs = boto3.client('ecs', region_name=AWS_REGION)
autoscaling = boto3.client('autoscaling', region_name=AWS_REGION)

# Returns the description of the provided auto scaling group by name.
def get_asg(asg_name):
    return autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[asg_name]
    )['AutoScalingGroups'][0]

# Blocks until the ECS cluster has the supplied count of active instances.
def wait_for_ecs_count(wanted_count, ecs_cluster, poll_interval):
    while True:
        container_instances = ecs.list_container_instances(cluster=ecs_cluster)['containerInstanceArns']
        active_count = len(container_instances)
        if active_count >= wanted_count:
            break
        sleep(poll_interval)

# Cleans up the temporary modifications made to the auto scaling group.
def cleanup(asg_name, desired_capacity, max_size):
    # Resume paused processes.
    autoscaling.resume_processes(
        AutoScalingGroupName=asg_name,
        ScalingProcesses=SUSPEND_PROCESSES
    )

    # Reset the desired capacity and max size.
    autoscaling.update_auto_scaling_group(
        AutoScalingGroupName=asg_name,
        MaxSize=max_size,
        DesiredCapacity=desired_capacity
    )

# AWS Lambda function entrypoint. Both arguments are ignored.
def handler(event, context):
    # Pause processes we don't want to occur during recycle.
    autoscaling.suspend_processes(
        AutoScalingGroupName=ASG_NAME,
        ScalingProcesses=SUSPEND_PROCESSES
    )

    # Retreive ASG details.
    asg = get_asg(ASG_NAME)

    # Retreive current container instances.
    pre_container_instance_arns = ecs.list_container_instances(
        cluster=ECS_CLUSTER
    )['containerInstanceArns']

    # Calculate new desired capacity.
    pre_desired_capacity = asg['DesiredCapacity']
    new_desired_capacity = pre_desired_capacity + 1

    # Calculate new max size.
    pre_max_size = asg['MaxSize']
    new_max_size = pre_max_size
    if new_desired_capacity > pre_max_size:
        new_max_size = new_desired_capacity

    # Increase desired count of instances in ASG.
    autoscaling.update_auto_scaling_group(
        AutoScalingGroupName=ASG_NAME,
        MaxSize=new_max_size,
        DesiredCapacity=new_desired_capacity
    )

    # Recycle each instance.
    i = 0
    for container_instance_arn in pre_container_instance_arns:
        i += 1

        # Wait for a new instance to join the ECS cluster.
        wait_for_ecs_count(new_desired_capacity, ECS_CLUSTER, POLL_INTERVAL)
        # Just to be safe...
        sleep(POLL_INTERVAL)

        # Drain the instance.
        ecs.update_container_instances_state(
            cluster=ECS_CLUSTER,
            containerInstances=[
                container_instance_arn
            ],
            status='DRAINING'
        )

        # Wait for container instance to fully drain.
        while True:
            container_instance = ecs.describe_container_instances(
                cluster=ECS_CLUSTER,
                containerInstances=[
                    container_instance_arn
                ]
            )['containerInstances'][0]
            if container_instance['runningTasksCount'] == 0:
                break
            sleep(POLL_INTERVAL)

        # Just to be safe...
        sleep(POLL_INTERVAL)

        # Don't terminate the final "extra" instance as the scale in will do that for us.
        if i >= pre_desired_capacity:
            break

        # Terminate instance.
        autoscaling.terminate_instance_in_auto_scaling_group(
            InstanceId=container_instance['ec2InstanceId'],
            ShouldDecrementDesiredCapacity=False
        )
        # It takes a little while for the terminated instance to be removed from the cluster.
        sleep(POLL_INTERVAL)

    cleanup(ASG_NAME, pre_desired_capacity, pre_max_size)

handler(False, False)
