

# Power off all nodes
# Delete bootstrap node
# Delete existing grub files & core user 
# Generate ignition files etc
# Create bootstrap 
# wait for bootstrap to be up 
# Set controllers to PXE on next boot
# Power on controllers
# Wait for all controllers to be up/in cluster
# Set computes to PXE on next boot
# Power on computes
# Wait for computes to be up 
# Approve certs for computes to join cluster
# Destroy Boostrap node

from auto_common import Ssh
import yaml
from ipmi import Ipmi 
import logging, sys 
import dracclient
from discover_nodes.dracclient.client import DRACClient
import subprocess, time
import requests, json


def load_settings():
    with open(r'/home/ansible/openshift-bare-metal/python/nodes.yaml') as file:
        settings = yaml.load(file)
    return settings

def load_inventory():
    with open(r'/home/ansible/openshift-bare-metal/ansible/generated_inventory') as file:
        inventory = yaml.load(file)
    return inventory

def set_node_to_pxe(idrac_ip, idrac_user, idrac_password):
    url = 'https://%s/redfish/v1/Systems/System.Embedded.1' % idrac_ip
    payload = {"Boot":{"BootSourceOverrideTarget":"Pxe"}}
    headers = {'content-type': 'application/json'}

    response = requests.patch(url, data=json.dumps(payload), headers=headers, verify=False,auth=(idrac_user, idrac_password))
    data = response.json()
    statusCode = response.status_code
    if statusCode == 200:
        print("Node set to Pxe on next boot")
    else:
        print("\n- Failed to set node to Pxe boot, errror code is %s" % statusCode)
        detail_message=str(response.__dict__)
        print(detail_message)
        


def deploy():
#    a_logger = logging.getLogger()
#    a_logger.setLevel(logging.INFO)

#    output_file_handler = logging.FileHandler("output.log")
#    stdout_handler = logging.StreamHandler(sys.stdout)

#    a_logger.addHandler(output_file_handler)
#    a_logger.addHandler(stdout_handler)

    print("- Clean up any existing instlal  ")
    cmds = [
        'virsh undefine --nvram "bootstrapkvm"',
        'virsh destroy bootstrapkvm',
        ' killall -u core',
        'userdel -r core',
        'rm -rf /var/lib/tftpboot/uefi/*'
    ]
    for cmd in cmds:
        Ssh.execute_command("localhost",
                            "root",
                            "Dell0SS!",
                            cmd)
    print ("- Power off control/compute nodes")
    settings = load_settings()
    all_nodes = settings['control_nodes'] + settings['compute_nodes']
    print(all_nodes)
    for node in all_nodes:
        print ("powering off " + node['name'])
        drac_ip = node["ip_idrac"]
        drac_user = "root"
        drac_password = 'Dell0SS!'

        drac_client = DRACClient(drac_ip, drac_user, drac_password)
        if "POWER_ON" in drac_client.get_power_state():
            drac_client.set_power_state('POWER_OFF')

    print("- Run ansible playbook to generate ignition files etc")
    subprocess.call('ansible-playbook -i generated_inventory haocp.yaml', shell=True, cwd='/home/ansible/openshift-bare-metal/ansible')
	
    
    print("- Create the bootstrap VM")
    inventory = load_inventory()
    bootstrap_mac = inventory['all']['vars']['bootstrap_node'][0]['mac']
    cmd = 'virt-install --name bootstrapkvm --ram 20480 --vcpu 8 --disk path=/home/bootstrapvm-disk.qcow2,format=qcow2,size=20 --os-variant generic --network=bridge=br0,model=virtio,mac=' + bootstrap_mac + ' --pxe --boot uefi,hd,network --noautoconsole &'
    print(" running " + cmd)
    re = Ssh.execute_command("localhost",
                            "root",
                            "Dell0SS!",
                            cmd)
    print(str(re))
    print("-  wait for the bootstrap Vm to pxe/install")
    bPXe_complete = False
    while bPXe_complete is False:
        re = Ssh.execute_command("localhost",
                                "root",
                                'Dell0SS!',
                                "virsh list --all | grep bootstrapkvm")[0]
        print(re)
        if "shut off" in re:
            bPXe_complete = True
        time.sleep(60)
    print("- Powering on the bootstrap VM")
    Ssh.execute_command("localhost",
                        "root",
                        "Dell0SS!",
                        "virsh start bootstrapkvm")

    print ("- Wait for the bootstrap VM to be ready")
    bBootstrap_ready = False
    while bBootstrap_ready is False:
        cmd = 'ssh -t root@localhost "sudo su - core -c \' ssh -o \\"StrictHostKeyChecking no \\" bootstrap sudo ss -tulpn | grep -E \\"6443|22623|2379\\"\'"'
        print(cmd)
        openedPorts= Ssh.execute_command_tty("localhost",
                                         "root",
                                         "Dell0SS!",
                                         cmd)
        if ("22623" in str(openedPorts)) and ("2379" in str(openedPorts)) and ("6443" in str(openedPorts)) :
            print(" ,, boostrap UP! ")
            bBootstrap_ready = True
        time.sleep(40)
    print("- Bootstrap VM is ready")

    print("- PXE boot the controller nodes")
    for node in settings['control_nodes']:
        set_node_to_pxe(node["ip_idrac"] ,'root','Dell0SS!')
        print("powering on " + str(node["ip_idrac"]))
        drac_client = DRACClient(node["ip_idrac"], drac_user, drac_password)
        if "POWER_OFF" in drac_client.get_power_state():
            drac_client.set_power_state('POWER_ON')




def main():
    deploy()
        

if __name__ == "__main__":
    main()


