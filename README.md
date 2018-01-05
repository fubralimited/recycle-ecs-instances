# recycle-ecs-instances

A script to recreate all container instances in an ECS cluster by utilising the
autoscaling group.

This script will increase the desired count of instances in the autoscaling
group, and then one by one drain and terminate instances in the ECS cluster
while waiting for the autoscaling group to pick up the slack and recreate them.

This is useful for rolling instances updates when combined with a full package
manager update included in the launch configuration's user data script.

At no point will you ever be running with fewer instances than you currently
are.

## Requirements

- Python 3
- [boto3](https://boto3.readthedocs.io/en/latest/)

You must have your ECS instances managed by an autoscaling group. There cannot
be more than 100 instances as part of the cluster.

`boto3` can be installed using `pip install boto3` or your system's package
manager may have packaged it for you.

This script may work with Python 2 but it has not been tested.

## Installation

Just yank the script from GitHub. Take a look at it if you like.

## Usage

```
python recycle-ecs-instances.py -h
```

## Support

Please file an issue on [this project](https://github.com/fubralimited/recycle-ecs-instances)
for support.

## Contributions

All contributions are welcome. To contribute, please file an issue noting your
request.

If you are able to work on this request yourself note this in the issue so
nobody else picks it up. A PR should be filed once the contribution has been
completed.

## License

[MIT](https://choosealicense.com/licenses/mit/).
