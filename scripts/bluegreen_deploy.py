import boto3
import sys
import datetime
import yaml
import time

from utils import *


elb_client = boto3.client('elbv2')
asg_client = boto3.client('autoscaling')
ec2_client = boto3.client('ec2')


def deploy(deploy_conf):
    # 1. Get Configurations From deploy.yml 

    lb_name = deploy_config["lb_name"]
    subnets = deploy_config["subnets"]
    sgs = deploy_config["sgs"]
    tgs_conf = deploy_config["tgs_conf"]
    asg_conf = deploy_config["asg_conf"]
    listener_conf = deploy_config["listener_conf"]

    # 2. Get loadbalancer Configurations, If it doen't exist then create loadbalancer
    lb = None
    try:
        lbs = get_lbs(elb_client, deploy_config["lb_name"])
        lb = lbs[0]
    except Exception as e:
        lb = create_lb(elb_client, lb_name, subnets, sgs)["LoadBalancers"][0]

    
    lb_dns = lb["DNSName"]
    lb_arn = lb["LoadBalancerArn"]
    vpc_id = lb["VpcId"]

    # 3. Get TargetGroups Configurations. If it doen't exist then create two TargetGroups.
    tgs_map = {}
    for tg_conf in tgs_conf:
        try:
            tg = get_tgs_by_name(elb_client, [tg_conf["name"]])[0]
            tgs_map[tg_conf["name"]] = tg
        except Exception as e:
            new_tg = create_tg(elb_client, tg_conf, vpc_id)[0]
            tgs_map[tg_conf["name"]] = new_tg
        
        
    # 4. Create TargetGroups Weight Informations.
    tg = tgs_map[deploy_conf["target_tg"]]
    tgs_weights = []

    for tg_key in tgs_map.keys():
        tmp_tg = tgs_map[tg_key]
        weight = 0
        if tmp_tg == tg:
            weight = 1

        tgs_weights.append({"TargetGroupArn": tmp_tg["TargetGroupArn"], "Weight": weight})
        
    tg_arn = tg["TargetGroupArn"]


    # 5. Get LaunchTemplate. set new LaunchTemplate number as old value + 1

    tpl_conf = deploy_config["tpl_conf"]
    tpls = get_launch_tpls(ec2_client, tpl_conf["name"])

    tpl = None
    tpl_num_id = 1
    tpl_old_num_id = 0

    if len(tpls) > 0:
        tpl_old_num_id = get_max_id(tpls, "LaunchTemplateName")
        tpl_num_id = tpl_old_num_id + 1

    tpl_name = tpl_conf["name"] + f"_{tpl_num_id}"

    # 6. Get AutoScalingGroup Configuration. add old value + 1 like LaunchTemplate
    asgs = get_asg(asg_client, asg_conf["name"])

    asg_num_id = 1
    asg_old_num_id = 0

    if len(asgs) > 0:
        asg_old_num_id = get_max_id(asgs, "AutoScalingGroupName")
        asg_num_id = asg_old_num_id + 1

    asg_name = asg_conf["name"] + f"_{asg_num_id}"

    # 7. Create new LaunchTemplate
    tpl = create_launch_tpl(ec2_client, tpl_name, tpl_conf, sgs)
    tpl_id = tpl["LaunchTemplateId"]

    # 8. Get LoadBalancer listener information.
    listeners = get_listeners(elb_client, lb_arn)
    listener = None
    if len(listeners) > 0:
        listener = listeners[0]
    else:
        listener = create_listener(elb_client, listener_conf, lb_arn, tgs_weights)[0]

    listener_arn = listener["ListenerArn"]

    # 9. Create AutoScalingGroup
    asgs = create_asg(asg_client, tpl_id, tg_arn, asg_name, asg_conf, subnets)
    while True:
        targets = check_target_health(elb_client, tg_arn)
        print(targets)
        tc, hc, new_targets = get_target_instances(targets)
        if hc >= asg_conf["desired_capacity"]:
            print("target group is healty")
            break
        else:
            print(f"total: {tc}, current_healthy_count: {hc}") 

        time.sleep(5)

    # 10. Change Listener Weight
    print("change listerner for target group")
    modify_listener(elb_client, listener_conf, listener_arn, tgs_weights)

    old_asg_name = asg_conf["name"] + f"_{asg_old_num_id}"

    # 11. Delete ASG
    while True:
        asg = get_asg(asg_client, old_asg_name)[0]
        size = len(asg["Instances"])
        if size == 0:
            print(f"old asg {old_asg_name} has no Instance")
            if asg_old_num_id > 0:
                delete_asg(asg_client, old_asg_name)
            old_tpl_name = tpl_conf["name"] + f"_{tpl_old_num_id}"
            if tpl_old_num_id > 0:
                delete_launch_tpl(ec2_client, old_tpl_name)

            break
        else:
            print(f"old asg {old_asg_name} has {size} Instances")
            print(asg["Instances"])
            

        time.sleep(5)


conf = read_config(sys.argv[1])
for deploy_config in conf:
    deploy(deploy_config)
