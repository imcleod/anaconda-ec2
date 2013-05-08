#!/usr/bin/python
#   Copyright (C) 2013 Red Hat, Inc.
#   Copyright (C) 2013 Ian McLeod <imcleod@redhat.com>
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

# Significant portions derived from Image Factory - http://imgfac.org/

import ozutil
import boto.ec2
import random
import logging 
import process_utils
import re
import os.path
from boto.exception import EC2ResponseError
from tempfile import NamedTemporaryFile
from time import sleep
from boto.ec2.blockdevicemapping import EBSBlockDeviceType, BlockDeviceMapping

# Boto is very verbose - shut it up
logging.getLogger('boto').setLevel(logging.INFO)

# Fedora 18 - i386 - EBS backed themselves
UTILITY_AMIS = { 'us-east-1':      [ 'ami-0d44cd64', 'sudo', 'ec2-user' ],
                 'us-west-2':      [ 'ami-6467ec54', 'sudo', 'ec2-user' ],
                 'us-west-1':      [ 'ami-de99b99b', 'sudo', 'ec2-user' ],
                 'eu-west-1':      [ 'ami-cafef1be', 'sudo', 'ec2-user' ],
                 'ap-southeast-1': [ 'ami-caa9eb98', 'sudo', 'ec2-user' ],
                 'ap-southeast-2': [ 'ami-dce771e6', 'sudo', 'ec2-user' ],
                 'ap-northeast-1': [ 'ami-7100ba70', 'sudo', 'ec2-user' ],
                 'sa-east-1':      [ 'ami-e5548cf8', 'sudo', 'ec2-user' ] }

# hd00 style (full disk image) v1.03
PVGRUB_AKIS =  { 'us-east-1':      { 'i386':'aki-b2aa75db' ,'x86_64':'aki-b4aa75dd' },
                 'us-west-2':      { 'i386':'aki-f637bac6' ,'x86_64':'aki-f837bac8' },
                 'us-west-1':      { 'i386':'aki-e97e26ac' ,'x86_64':'aki-eb7e26ae' },
                 'eu-west-1':      { 'i386':'aki-89655dfd' ,'x86_64':'aki-8b655dff' },
                 'ap-southeast-1': { 'i386':'aki-f41354a6' ,'x86_64':'aki-fa1354a8' },
                 'ap-southeast-2': { 'i386':'aki-3f990e05' ,'x86_64':'aki-3d990e07' },
                 'ap-northeast-1': { 'i386':'aki-3e99283f' ,'x86_64':'aki-40992841' },
                 'sa-east-1':      { 'i386':'aki-ce8f51d3' ,'x86_64':'aki-c88f51d5' } }


def wait_for_ec2_instance_state(instance, log, final_state='running', timeout=300):
    for i in range(timeout):
        if i % 10 == 0:
            log.debug("Waiting for EC2 instance to enter state (%s): %d/%d" % (final_state,i,timeout))
        try:
            instance.update()
        except EC2ResponseError, e:
            # We occasionally get errors when querying an instance that has just started - ignore them and hope for the best
            log.warning("EC2ResponseError encountered when querying EC2 instance (%s) - trying to continue" % (instance.id), exc_info = True)
        except:
            log.error("Exception encountered when updating status of instance (%s)" % (instance.id), exc_info = True)
            try:
                terminate_instance(instance)
            except:
                log.warning("WARNING: Instance (%s) failed to enter state (%s) and will not terminate - it may still be running" % (instance.id, final_state), exc_info = True)
                raise Exception("Instance (%s) failed to fully start or terminate - it may still be running" % (instance.id))
            raise Exception("Exception encountered when waiting for instance (%s) enter state (%s)" % (instance.id, final_state))
        if instance.state == final_state:
            break
        sleep(1)

    if instance.state != final_state:
        try:
            terminate_instance(instance)
        except:
            log.warning("WARNING: Instance (%s) failed to enter state (%s) and will not terminate - it may still be running" % (instance.id, final_state), exc_info = True)
            raise Exception("Instance (%s) failed to enter desired state (%s) - it may still be running" % (instance.id, final_state))
        raise Exception("Instance failed to start after %d seconds - stopping" % (timeout))


def terminate_instance(instance):
    # boto 1.9 claims a terminate() method but does not implement it
    # boto 2.0 throws an exception if you attempt to stop() an S3 backed instance
    # introspect here and do the best we can
    if "terminate" in dir(instance):
        instance.terminate()
    else:
        instance.stop()


class AMIHelper(object):

    def __init__(self, ec2_region, access_key, secret_key):
        super(AMIHelper, self).__init__()
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        try:
            self.region = boto.ec2.get_region(ec2_region, aws_access_key_id=access_key, aws_secret_access_key=secret_key)
            self.conn = self.region.connect(aws_access_key_id=access_key, aws_secret_access_key=secret_key)
        except Exception as e:
            self.log.error("Exception while attempting to establish EC2 connection")
            raise
        self.security_group = None
        self.instance = None

    def register_ebs_ami(self, snapshot_id, arch = 'x86_64', default_ephem_map = True,
                         img_name = None, img_desc = None):
        # register against snapshot
        try:
            aki=PVGRUB_AKIS[self.region.name][arch]
        except KeyError:
            raise Exception("Unable to determine pvgrub hd00 AKI for region (%s) arch (%s)" % (self.region.name, arch))

        if not img_name:
            rand_id = random.randrange(2**32)
            # These names need to be unique, hence the pseudo-uuid
            img_name='EBSHelper AMI - %s - uuid-%x' % (snapshot_id, rand_id)
        if not img_desc:
            img_desc='Created directly from volume snapshot %s' % (snapshot_id)

        self.log.debug("Registering snapshot (%s) as new EBS AMI" % (snapshot_id))
        ebs = EBSBlockDeviceType()
        ebs.snapshot_id = snapshot_id
        ebs.delete_on_termination = True
        block_map = BlockDeviceMapping()
        block_map['/dev/sda'] = ebs
        # The ephemeral mappings are automatic with S3 images
        # For EBS images we need to make them explicit
        # These settings are required to make the same fstab work on both S3 and EBS images
        if default_ephem_map:
            e0 = EBSBlockDeviceType()
            e0.ephemeral_name = 'ephemeral0'
            e1 = EBSBlockDeviceType()
            e1.ephemeral_name = 'ephemeral1'
            block_map['/dev/sdb'] = e0
            block_map['/dev/sdc'] = e1
        result = self.conn.register_image(name=img_name, description=img_desc,
                           architecture=arch,  kernel_id=aki,
                           root_device_name='/dev/sda', block_device_map=block_map)
        return str(result)


    def launch_wait_snapshot(self, ami, user_data, img_size = 10, img_name = None, img_desc = None,
                             remote_access_cmd = None):

        if not img_name:
            rand_id = random.randrange(2**32)
            # These names need to be unique, hence the pseudo-uuid
            img_name = 'EBSHelper AMI - %s - uuid-%x' % (ami, rand_id)
        if not img_desc:
            img_desc = 'Created from modified snapshot of AMI %s' % (ami)

        try:
            ami = self._launch_wait_snapshot(ami, user_data, img_size, img_name, img_desc, remote_access_cmd)
        finally:
            if self.security_group:
                try:
                    self.security_group.delete()
                except:
                    self.log.warning("Had a temporary security group but failed to delete it on EC2 - group may still be present")

            # TODO: This is sometimes redundant - try to clean up
            if self.instance:
                try:
                    self.instance.update()
                    if self.instance.state != 'terminated':
                        terminate_instance(self.instance)
                except:
                    self.log.warning("Still have an instance object but either could not query or could not terminate")
        return ami


    def _launch_wait_snapshot(self, ami, user_data, img_size = 10, img_name = None, img_desc = None,
                             remote_access_command = None):

        rand_id = random.randrange(2**32)
        # Modified from code taken from Image Factory 
        # Create security group
        security_group_name = "ebs-helper-vnc-tmp-%x" % (rand_id)
        security_group_desc = "Temporary security group with SSH access generated by EBSHelper python object"
        self.log.debug("Creating temporary security group (%s)" % (security_group_name))
        self.security_group = self.conn.create_security_group(security_group_name, security_group_desc)
        self.security_group.authorize('tcp', 22, 22, '0.0.0.0/0')
        self.security_group.authorize('tcp', 5900, 5950, '0.0.0.0/0')

        ebs_root = EBSBlockDeviceType()
        ebs_root.size=img_size
        ebs_root.delete_on_termination = True
        block_map = BlockDeviceMapping()
        block_map['/dev/sda'] = ebs_root

        # Now launch it
        instance_type="m1.small"
        self.log.debug("Starting ami %s in region %s with instance_type %s" % (ami, self.region.name, instance_type))

        reservation = self.conn.run_instances(ami, max_count=1, instance_type=instance_type, 
                                              user_data = user_data,
                                              security_groups = [ security_group_name ],
                                              block_device_map = block_map)
        # I used to have a check for more than one instance here -- but that would be a profound bug in boto
        if len(reservation.instances) == 0:
            raise Exception("Attempt to start instance failed")

        self.instance = reservation.instances[0]

        wait_for_ec2_instance_state(self.instance, self.log, final_state='running', timeout=300)

        self.log.debug("Instance (%s) is now running" % self.instance.id)
        self.log.debug("Public DNS will be: %s" % self.instance.public_dns_name)
        self.log.debug("Now waiting up to 30 minutes for instance to stop")

        wait_for_ec2_instance_state(self.instance, self.log, final_state='stopped', timeout=1800)

        # Snapshot
        self.log.debug("Creating a new EBS backed image from completed/stopped EBS instance")
        new_ami_id = self.conn.create_image(self.instance.id, img_name, img_desc)
        self.log.debug("boto creat_image call returned AMI ID: %s" % (new_ami_id))
        self.log.debug("Waiting for newly generated AMI to become available")
        # As with launching an instance we have seen occasional issues when trying to query this AMI right
        # away - give it a moment to settle
        sleep(10)
        new_amis = self.conn.get_all_images([ new_ami_id ])
        new_ami = new_amis[0]
        timeout = 120
        interval = 10
        for i in range(timeout):
            new_ami.update()
            if new_ami.state == "available":
                break
            elif new_ami.state == "failed":
                raise Exception("Amazon reports EBS image creation failed")
            self.log.debug("AMI status (%s) - waiting for 'available' - [%d of %d seconds elapsed]" % (new_ami.state, i * interval, timeout * interval))
            sleep(interval)

        self.log.debug("Terminating/deleting instance")
        terminate_instance(self.instance)
 
        if new_ami.state != "available":
            raise Exception("Failed to produce an AMI ID")

        self.log.debug("SUCCESS: %s is now available for launch" % (new_ami_id))

        return new_ami_id


class EBSHelper(object):

    def __init__(self, ec2_region, access_key, secret_key, utility_ami = None, command_prefix = None, user = 'root'):
        super(EBSHelper, self).__init__()
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        try:
            self.region = boto.ec2.get_region(ec2_region, aws_access_key_id=access_key, aws_secret_access_key=secret_key)
            self.conn = self.region.connect(aws_access_key_id=access_key, aws_secret_access_key=secret_key)
        except Exception as e:
            self.log.error("Exception while attempting to establish EC2 connection")
            raise
        if not utility_ami:
            self.utility_ami = UTILITY_AMIS[ec2_region][0]
            self.command_prefix = UTILITY_AMIS[ec2_region][1]
            self.user = UTILITY_AMIS[ec2_region][2]
        else:
            self.utility_ami = utility_ami
            self.command_prefix = command_prefix
            self.user = user
        self.instance = None
        self.security_group = None
        self.key_name = None
        self.key_file_object = None


    def safe_upload_and_shutdown(self, image_file):
        """
        Launch the AMI - terminate
        upload, create volume and then terminate
        """
        if self.instance:
            raise Exception("Safe upload can only be used when the utility instance is not already running")

        self.start_ami()
        try:
            snapshot = self.file_to_snapshot(image_file)
        finally:
            self.terminate_ami()

        return snapshot

    def start_ami(self):
        try:
            self._start_ami()
        except Exception as e:
            self.log.error("Exception while starting AMI - cleaning up")
            self.log.exception(e)
            self.terminate_ami()


    def _start_ami(self):
        rand_id = random.randrange(2**32)
        # Modified from code taken from Image Factory 
        # Create security group
        security_group_name = "ebs-helper-tmp-%x" % (rand_id)
        security_group_desc = "Temporary security group with SSH access generated by EBSHelper python object"
        self.log.debug("Creating temporary security group (%s)" % (security_group_name))
        self.security_group = self.conn.create_security_group(security_group_name, security_group_desc)
        self.security_group.authorize('tcp', 22, 22, '0.0.0.0/0')

        # Create a use-once SSH key
        self.log.debug("Creating SSH key pair for image upload")
        self.key_name = "ebs-helper-tmp-%x" % (rand_id)
        self.key = self.conn.create_key_pair(self.key_name)
        # Shove into a named temp file
        self.key_file_object = NamedTemporaryFile()
        self.key_file_object.write(self.key.material)
        self.key_file_object.flush()
        self.log.debug("Temporary key is stored in (%s)" % (self.key_file_object.name))

        # Now launch it
        instance_type="m1.small"
        self.log.debug("Starting ami %s in region %s with instance_type %s" % (self.utility_ami, self.region.name, instance_type))

        reservation = self.conn.run_instances(self.utility_ami, max_count=1, instance_type=instance_type, key_name=self.key_name, security_groups = [ security_group_name ])
        # I used to have a check for more than one instance here -- but that would be a profound bug in boto
        if len(reservation.instances) == 0:
            raise Exception("Attempt to start instance failed")

        self.instance = reservation.instances[0]
        #self.wait_for_ec2_instance_start(self.instance)
        wait_for_ec2_instance_state(self.instance, self.log, final_state='running', timeout=300)
        self.wait_for_ec2_ssh_access(self.instance.public_dns_name, self.key_file_object.name)
        self.enable_root(self.instance.public_dns_name, self.key_file_object.name, self.user, self.command_prefix) 


    def terminate_ami(self):
        # Terminate the AMI and delete all local and remote artifacts
        # Try very hard to do whatever is possible here and warn loudly if something
        # may have been left behind

        # Remove local copy of the key
        if self.key_file_object:
            try:
                self.key_file_object.close()
            except:
                self.log.warning("Had temporary key file object but could not close - key may still be on local fs")

        # Remove remote copy of the key
        if self.key_name:
            try:
                self.conn.delete_key_pair(key_name)
            except:
                self.log.warning("Had local key name (%s) but failed to delete on EC2 - key may still be present" % (self.key_name))

        # Terminate the instance
        if self.instance:
            try:
                self.terminate_instance(self.instance)
                timeout = 60
                interval = 5
                for i in range(timeout):
                    self.instance.update()
                    if(self.instance.state == "terminated"):
                        break
                    elif(i < timeout):
                        self.log.debug("Instance status (%s) - waiting for 'terminated'. [%d of %d seconds elapsed]" % (self.instance.state, i * interval, timeout * interval))
                        sleep(interval)
                    else:
                        self.log.warining("Timeout waiting for instance to terminate.")
            except:
                self.log.warning("Had instance object but failed to terminate - instance may still be running")

        # If we do have an instance it must be terminated before this can happen
        # That is why we put it last
        # Try even if we get an exception while doing the termination above
        if self.security_group:
            try:
                self.security_group.delete()
            except:
                self.log.warning("Had a temporary security group but failed to delete it on EC2 - group may still be present")


    def file_to_snapshot(self, filename, compress=True):
        # TODO: Add a conservative exception handler over the top of this to delete all remote artifacts on
        #       an exception

        if not self.instance:
            raise Exception("You must start the utility instance with start_ami() before uploading files to volumes")

        if not os.path.isfile(filename):
            raise Exception("Filename (%s) is not a file" % filename)

        filesize = os.path.getsize(filename)
        # Gigabytes, rounded up
        volume_size = int( (filesize/(1024 ** 3)) + 1 )

        self.log.debug("Creating %d GiB volume in (%s) to hold new image" % (volume_size, self.instance.placement))
        volume = self.conn.create_volume(volume_size, self.instance.placement) 

        # Volumes can sometimes take a very long time to create
        # Wait up to 10 minutes for now (plus the time taken for the upload above)
        self.log.debug("Waiting up to 600 seconds for volume (%s) to become available" % (volume.id))
        retcode = 1
        for i in range(60):
            volume.update()
            if volume.status == "available":
                retcode = 0
                break
            self.log.debug("Volume status (%s) - waiting for 'available': %d/600" % (volume.status, i*10))
            sleep(10)

        if retcode:
            raise Exception("Unable to create target volume for EBS AMI - aborting")

        # Volume is now available
        # Attach it
        self.conn.attach_volume(volume.id, self.instance.id, "/dev/sdh")

        self.log.debug("Waiting up to 120 seconds for volume (%s) to become in-use" % (volume.id))
        retcode = 1
        for i in range(12):
            volume.update()
            vs = volume.attachment_state()
            if vs == "attached":
                retcode = 0
                break
            self.log.debug("Volume status (%s) - waiting for 'attached': %d/120" % (vs, i*10))
            sleep(10)

        if retcode:
            raise Exception("Unable to attach volume (%s) to instance (%s) aborting" % (volume.id, self.instance.id))

        # TODO: This may not be necessary but it helped with some funnies observed during testing
        #         At some point run a bunch of builds without the delay to see if it breaks anything
        self.log.debug("Waiting 20 seconds for EBS attachment to stabilize")
        sleep(20)

        # Decompress image into new EBS volume
        self.log.debug("Copying file into volume")

        # This is big and hairy - it also works, and avoids temporary storage on the local and remote
        # side of this activity
        
        command = 'gzip -c %s | ' % filename
        command += 'ssh -i %s -F /dev/null  -o ServerAliveInterval=30 -o StrictHostKeyChecking=no ' % self.key_file_object.name
        command += '-o ConnectTimeout=30 -o UserKnownHostsFile=/dev/null -o PasswordAuthentication=no '
        command += 'root@%s "gzip -d -c | dd of=/dev/xvdh bs=4k"' % self.instance.public_dns_name

        self.log.debug("Command will be:\n\n%s\n\n" % command)

        self.log.debug("Running.  This may take some time.")
        process_utils.subprocess_check_output([ command ], shell=True)

        # Sync before snapshot
        process_utils.ssh_execute_command(self.instance.public_dns_name, self.key_file_object.name, "sync")

        # Snapshot EBS volume
        self.log.debug("Taking snapshot of volume (%s)" % (volume.id))
        snapshot = self.conn.create_snapshot(volume.id, 'EBSHelper snapshot of file "%s"' % filename)

        # This can take a _long_ time - wait up to 20 minutes
        self.log.debug("Waiting up to 1200 seconds for snapshot (%s) to become completed" % (snapshot.id))
        retcode = 1
        for i in range(120):
            snapshot.update()
            if snapshot.status == "completed":
                retcode = 0
                break
            self.log.debug("Snapshot progress(%s) -  status (%s) - waiting for 'completed': %d/1200" % (str(snapshot.progress), snapshot.status, i*10))
            sleep(10)

        if retcode:
            raise Exception("Unable to snapshot volume (%s) - aborting" % (volume.id))

        self.log.debug("Successful creation of snapshot (%s)" % (snapshot.id))

        self.log.debug("Detaching volume (%s)" % volume.id)
        volume.detach()

        self.log.debug("Waiting up to 120 seconds for volume (%s) to become detached (available)" % (volume.id))
        retcode = 1
        for i in range(12):
            volume.update()
            if volume.status == "available":
                retcode = 0
                break
            self.log.debug("Volume status (%s) - waiting for 'available': %d/120" % (volume.status, i*10))
            sleep(10)

        if retcode:
            raise Exception("Unable to detach volume - WARNING - volume may persist and cost money!")

        self.log.debug("Deleting volume")
        volume.delete()
        # TODO: Verify delete

        return snapshot.id


    def wait_for_ec2_ssh_access(self, guestaddr, sshprivkey):
        self.log.debug("Waiting for SSH access to EC2 instance (User: %s)" % self.user)
        for i in range(300):
            if i % 10 == 0:
                self.log.debug("Waiting for EC2 ssh access: %d/300" % (i))

            try:
                process_utils.ssh_execute_command(guestaddr, sshprivkey, "/bin/true", user=self.user)
                break
            except:
                pass

            sleep(1)

        if i == 299:
            raise Exception("Unable to gain ssh access after 300 seconds - aborting")


    def wait_for_ec2_instance_start(self, instance):
        self.log.debug("Waiting for EC2 instance to become active")
        for i in range(300):
            if i % 10 == 0:
                self.log.debug("Waiting for EC2 instance to start: %d/300" % (i))
            try:
                instance.update()
            except EC2ResponseError, e:
                # We occasionally get errors when querying an instance that has just started - ignore them and hope for the best
                self.log.warning("EC2ResponseError encountered when querying EC2 instance (%s) - trying to continue" % (instance.id), exc_info = True)
            except:
                self.log.error("Exception encountered when updating status of instance (%s)" % (instance.id), exc_info = True)
                self.status="FAILED"
                try:
                    self.terminate_instance(instance)
                except:
                    self.log.warning("WARNING: Instance (%s) failed to start and will not terminate - it may still be running" % (instance.id), exc_info = True)
                    raise Exception("Instance (%s) failed to fully start or terminate - it may still be running" % (instance.id))
                raise Exception("Exception encountered when waiting for instance (%s) to start" % (instance.id))
            if instance.state == u'running':
                break
            sleep(1)

        if instance.state != u'running':
            self.status="FAILED"
            try:
                self.terminate_instance(instance)
            except:
                self.log.warning("WARNING: Instance (%s) failed to start and will not terminate - it may still be running" % (instance.id), exc_info = True)
                raise Exception("Instance (%s) failed to fully start or terminate - it may still be running" % (instance.id))
            raise Exception("Instance failed to start after 300 seconds - stopping")


    def terminate_instance(self, instance):
        # boto 1.9 claims a terminate() method but does not implement it
        # boto 2.0 throws an exception if you attempt to stop() an S3 backed instance
        # introspect here and do the best we can
        if "terminate" in dir(instance):
            instance.terminate()
        else:
            instance.stop()

    def enable_root(self,guestaddr, sshprivkey, user, prefix):
        for cmd in ('mkdir /root/.ssh',
                    'chmod 600 /root/.ssh',
                    'cp -f /home/%s/.ssh/authorized_keys /root/.ssh' % user,
                    'chmod 600 /root/.ssh/authorized_keys'):
            try:
                process_utils.ssh_execute_command(guestaddr, sshprivkey, cmd, user=user, prefix=prefix)
            except Exception as e:
                pass

        try:
            stdout, stderr, retcode = process_utils.ssh_execute_command(guestaddr, sshprivkey, '/bin/id')
            if not re.search('uid=0', stdout):
                raise Exception('Running /bin/id on %s as root: %s' % (guestaddr, stdout))
        except Exception as e:
            raise Exception('Transfer of authorized_keys to root from %s must have failed - Aborting - %s' % (user, e))
