#!/usr/bin/python


# A set of helpful utility functions
# Avoid imports that are too specific to a given cloud or OS
# We want to allow people to import all of these
# Add logging option

import os
import re
import subprocess

def subprocess_check_output(*popenargs, **kwargs):
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')

    process = subprocess.Popen(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, *popenargs, **kwargs)

    stdout, stderr = process.communicate()
    retcode = process.poll()

    if retcode:
        cmd = ' '.join(*popenargs)
        raise Exception("'%s' failed(%d): %s" % (cmd, retcode, stderr))
    return (stdout, stderr, retcode)

def subprocess_check_output_pty(*popenargs, **kwargs):
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')

    (master, slave) = os.openpty()
    process = subprocess.Popen(stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, *popenargs, **kwargs)

    stdout, stderr = process.communicate()
    retcode = process.poll()

    os.close(slave)
    os.close(master)

    if retcode:
        cmd = ' '.join(*popenargs)
        raise Exception("'%s' failed(%d): %s" % (cmd, retcode, stderr))
    return (stdout, stderr, retcode)

def ssh_execute_command(guestaddr, sshprivkey, command, timeout=10, user='root', prefix=None):
    """
    Function to execute a command on the guest using SSH and return the output.
    Modified version of function from ozutil to allow us to deal with non-root
    authorized users on ec2
    """
    # ServerAliveInterval protects against NAT firewall timeouts
    # on long-running commands with no output
    #
    # PasswordAuthentication=no prevents us from falling back to
    # keyboard-interactive password prompting
    #
    # -F /dev/null makes sure that we don't use the global or per-user
    # configuration files
    #
    # -t -t ensures we have a pseudo tty for sudo

    cmd = ["ssh", "-i", sshprivkey,
            "-F", "/dev/null",
            "-o", "ServerAliveInterval=30",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=" + str(timeout),
            "-o", "UserKnownHostsFile=/dev/null",
            "-t", "-t",
            "-o", "PasswordAuthentication=no"]

    if prefix:
        command = prefix + " " + command

    cmd.extend(["%s@%s" % (user, guestaddr), command])

    if(prefix == 'sudo'):
        return subprocess_check_output_pty(cmd)
    else:
        return subprocess_check_output(cmd)

def enable_root(guestaddr, sshprivkey, user, prefix):
    for cmd in ('mkdir /root/.ssh',
                'chmod 600 /root/.ssh',
                'cp /home/%s/.ssh/authorized_keys /root/.ssh' % user,
                'chmod 600 /root/.ssh/authorized_keys'):
        try:
            ssh_execute_command(guestaddr, sshprivkey, cmd, user=user, prefix=prefix)
        except Exception as e:
            pass

    try:
        stdout, stderr, retcode = ssh_execute_command(guestaddr, sshprivkey, '/bin/id')
        if not re.search('uid=0', stdout):
            raise Exception('Running /bin/id on %s as root: %s' % (guestaddr, stdout))
    except Exception as e:
        raise Exception('Transfer of authorized_keys to root from %s must have failed - Aborting - %s' % (user, e))
