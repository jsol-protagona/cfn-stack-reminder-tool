"""Lambda for Cfn Stack Removal Reminder."""
import os
from datetime import datetime
from operator import itemgetter

import boto3


def create_cfn_client():
    """Create a CFN Client."""
    return boto3.client("cloudformation")


def create_sns_client():
    """Create a SNS Client."""
    return boto3.client("sns")


def create_sts_client():
    """Create a STS Client."""
    return boto3.client("sts")


def retrieve_stacks(region: str):
    """Retrieve the CFN Stacks."""
    os.environ["AWS_DEFAULT_REGION"] = region
    cfn = create_cfn_client()

    active_stack_status = [
        "CREATE_IN_PROGRESS",
        "CREATE_FAILED",
        "CREATE_COMPLETE",
        "ROLLBACK_IN_PROGRESS",
        "ROLLBACK_FAILED",
        "ROLLBACK_COMPLETE",
        "UPDATE_IN_PROGRESS",
        "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS",
        "UPDATE_COMPLETE",
        "UPDATE_ROLLBACK_IN_PROGRESS",
        "UPDATE_ROLLBACK_FAILED",
        "UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS",
        "UPDATE_ROLLBACK_COMPLETE",
        "REVIEW_IN_PROGRESS",
    ]

    """
    Retrieves all stacks in region
    """

    return cfn.list_stacks(StackStatusFilter=active_stack_status)


def lambda_handler(event, context):
    """Sorts stacks and sends reminders."""
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    sts = create_sts_client()
    sns = create_sns_client()
    account_id = sts.get_caller_identity()["Account"]
    namespace = os.getenv("NAMESPACE")
    department = os.getenv("DEPARTMENT")

    # Timestamp details
    dt = datetime.now()
    nowstr = dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    now = datetime.strptime(nowstr, "%Y-%m-%d %H:%M:%S.%f")

    # Remove stacks we expect to exist in the account
    east_one_stacks = retrieve_stacks("us-east-1")
    west_two_stacks = retrieve_stacks("us-west-2")
    all_stacks = east_one_stacks["StackSummaries"] + west_two_stacks["StackSummaries"]
    sorted_stacks = sorted(all_stacks, key=itemgetter("CreationTime"))
    stripped_stacks = []
    for stack in sorted_stacks:
        stack_id = stack["StackId"]
        stack_region = stack_id[23:32]
        stack_name = stack["StackName"]
        stack_creation_date = stack["CreationTime"]
        if "stack-reminder" not in stack_name:
            if "." in (str(stack_creation_date)):
                ts = datetime.strptime(
                    str(stack_creation_date), "%Y-%m-%d %H:%M:%S.%f%z"
                )
            else:
                ts = datetime.strptime(
                    str(stack_creation_date), "%Y-%m-%d %H:%M:%S%z"
                )
            ts = ts.replace(tzinfo=None)
            difference = now - ts
            age = difference.days
            name_date = {"region": stack_region, "name": stack_name, "age": age}
            stripped_stacks.append(name_date)
    stack_name_len = 0
    stack_list_under_5 = []
    stack_list_over_5 = []
    stack_list_over_30 = []
    for stack in stripped_stacks:
        for key, value in stack.items():
            if key == "region":
                name_age = value
            elif key == "name":
                name_age = name_age + "    " + value
                stack_length = len(value)
                if stack_length > stack_name_len:
                    stack_name_len = stack_length
                    spaces = stack_name_len
                else:
                    d = stack_name_len - stack_length
                    spaces = stack_name_len + d
                name_age = name_age + " " * spaces
            elif key == "age":
                if value >= 31:
                    name_age = name_age + " " + str(value)
                    stack_list_over_30.append(name_age)
                if value >= 6 and value <= 30:
                    name_age = name_age + " " + str(value)
                    stack_list_over_5.append(name_age)
                if value <= 5:
                    name_age = name_age + " " + str(value)
                    stack_list_under_5.append(name_age)
    message = []
    combined_list = []

    if len(stripped_stacks) < 1:
        # There are no stacks in account, reminder email will not be sent to user.
        return {"status_code": 300}  # noqa: W291

    message.append(
        "This is a reminder of existing stacks in your account: " + str({account_id})
    )
    message.append(
        "Please destroy any stacks that are no longer in use to reduce costs"
    )
    combined_list.append(message)
    if len(stack_list_over_30) >= 1:
        stack_list_over_30.insert(0, "___________________________________________")
        stack_list_over_30.insert(1, "Stacks are over 30 days old")
        stack_list_over_30.insert(2, "___________________________________________")
        stack_list_over_30.insert(
            3, "Region         | Stack Name" + " " * stack_name_len + "| Age     "
        )
        stack_list_over_30.insert(
            4, "-----------------------------------------------------------------------"
        )
        combined_list.append(stack_list_over_30)
    if len(stack_list_over_5) >= 1:
        stack_list_over_5.insert(0, "___________________________________________")
        stack_list_over_5.insert(1, "Stacks are over 5 days old")
        stack_list_over_5.insert(2, "___________________________________________")
        stack_list_over_5.insert(
            3, "Region         | Stack Name" + " " * stack_name_len + "| Age     "
        )
        stack_list_over_5.insert(
            4, "-----------------------------------------------------------------------"
        )
        combined_list.append(stack_list_over_5)
    if len(stack_list_under_5) >= 1:
        stack_list_under_5.insert(0, "___________________________________________")
        stack_list_under_5.insert(1, "Stacks are less than 5 days old")
        stack_list_under_5.insert(2, "___________________________________________")
        stack_list_under_5.insert(
            3, "Region         | Stack Name" + " " * stack_name_len + "| Age     "
        )
        stack_list_under_5.insert(
            4, "-----------------------------------------------------------------------"
        )
        combined_list.append(stack_list_under_5)

    lines = "\n".join(sum(combined_list, []))

    """
    Post SNS Message
    """
    topic_arn = f"arn:aws:sns:us-east-1:{account_id}:{department}-{namespace}-cfn-stack-removal-reminder"  # noqa
    response = sns.publish(  # noqa: F841
        TopicArn=topic_arn,
        Message=lines,
        Subject=f"Stack Removal Reminder for {account_id}",
    )

    return {"status_code": 200}  # noqa: W291
