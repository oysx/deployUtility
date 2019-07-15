#!/usr/bin/python
import subprocess
import time

from viConfig import viConfig
gcall = None
gOptions = {}

GUEST_STAT_STARTED = 'started'
GUEST_STAT_STOPPED = 'stopped'
GUEST_STAT_NOEXIST = 'noexist'

def myprint(*args):
	curtime = time.strftime("%Y/%M/%d-%H:%M:%S ")
	print(curtime+args[0] % args[1:])
	
class mycall:
	def __init__(self):
		self.tasks = []

	def acall(self, *args, **kwargs):
		show = kwargs.get('show')
		if show:
			myprint(str(*args))
		try:
			task = subprocess.Popen(*args, shell=True)
			self.tasks.append(task)
		except Exception as e:
			print "Exe: %s encounter Exception: %s" % (str(*args), str(e))

		if show:
			myprint("acall Done")
		return True

	def scall(self, *args, **kwargs):
		show = kwargs.get('show')
		if show:
			myprint(str(*args))
		try:
			result = subprocess.call(*args, shell=True)
		except Exception as e:
			print "Exe: %s encounter Exception: %s" % (str(*args), str(e))
			result = False
			
		if show:
			myprint("scall Done: %s" % str(result))
		return result

	def await(self):
		for task in self.tasks:
			print "Waiting for %s" % (str(task))
			task.wait()

		self.tasks = []
		return True

def viPasswdHelper(remote):
	askPass = 'viAskPass-%s-%s.sh' % (remote.ip, remote.user)
	
	gcall.scall('''
cat > %s <<EOF
#!/bin/bash
echo "%s"
EOF
''' % (askPass, remote.passwd))
	gcall.scall('chmod a+x %s' % askPass)
	return askPass

class viGuest:
	def __init__(self, ip):
		for guest in viConfig.guests:
			if guest.get('ip') == ip:
				self.guest = guest
				break
	
	def getConfig(self):
		return self.guest
	
	def createInstance(self, hostRemote):
		cmd = self.guest.get('type') or viConfig.DEF_GUEST_TYPE
		cmd += '(%s, %s)' % ('hostRemote', 'self.guest')
		return eval(cmd)
	
class viHost:
	def __init__(self, remote, guestIp):
		self.guestIp = guestIp
		self.remote = remote
				
	def prepare(self):
		self.remote.sexe('mkdir -p ~/{0}'.format(viConfig.workDir))
		
		#create passwd helper file
		self.remote.askPass = viPasswdHelper(self.remote)
		
		self.remote.cp('./*.*', '~/{0}'.format(viConfig.workDir))
		
	def setup(self):
		guest = viGuest(self.guestIp)
		guest = guest.createInstance(self.remote)
		guest.run()
				
class viRemote:
	def __init__(self, ip, user, passwd, log):
		self.ip = ip
		self.user = user
		self.passwd = passwd
		self.log = log
		
		self.prefix = 'sshpass -p {0} ssh -q -o StrictHostKeyChecking=no {1}@{2} '.format(self.passwd, self.user, self.ip, viConfig.workDir)
	
		gcall.scall('echo "" > {0}'.format(self.log))
		
	def cp(self, src, dst, show=False):
		result = gcall.scall("sshpass -p {0} scp -q -o StrictHostKeyChecking=no {1} {2}@{3}:{4} 2>&1 >> {5}".format(self.passwd, src, self.user, self.ip, dst, self.log), show=show)
		if result != 0:
			myprint("remote cp failed: {0}!".format(str(dst)))

	def sexe(self, cmd, show=False):
		return gcall.scall('{0} "{1}" 2>>{2} >> {2}'.format(self.prefix, cmd, self.log), show=show)

	def aexe(self, cmd, show=False):
		gcall.acall('{0} "{1}" 2>>{2} >> {2}'.format(self.prefix, cmd, self.log), show=show)





class viDocker:
	def __init__(self, remote, guest):
		self.ip = guest.get('ip')
		self.guest = guest
		self.remote = remote
		self.sudo_a = 'SUDO_ASKPASS=/home/%s/%s/%s sudo -A' % (self.remote.user, viConfig.workDir, self.remote.askPass)
		
	def isStarted(self):
		result = self.remote.sexe('''{0} docker ps -f name=vivi_{1} | grep vivi_{1} 2>&1 > /dev/null'''.format(self.sudo_a, self.ip))
		return result == 0
		
	def isStopped(self):
		result = self.remote.sexe('''{0} docker ps -a -f name=vivi_{1} | grep vivi_{1} 2>&1 > /dev/null'''.format(self.sudo_a, self.ip))
		return result == 0
		
	def construstCmds(self, cmds):
		output = ""
		for cmd in cmds:
			output += "{0} docker exec -u root vivi_{1} bash -c '".format(self.sudo_a, self.ip) + cmd + "';"
		return output
	
	def onStartupCmds(self):
		prefix_length = self.guest.get('prefix_length') or viConfig.DEF_GUEST_PREFIX_LENGTH
		cmds = ["ifconfig eth0 {0}/{1}; service ssh start".format(self.ip, prefix_length)]
		return self.construstCmds(cmds)
	
	def onRestartCmds(self):
		cmds = ["ifdown eth0; ifup eth0",
				"/etc/init.d/rc 2",
				"cron"]
		return self.construstCmds(cmds)
	
	def run(self):
		#firstly decide whether the container is running
		if self.isStarted():
			self.guest['status'] = GUEST_STAT_STARTED
			myprint("docker for vivi_%s is running" % self.ip)
			self.remote.sexe('''rm ~/{0}/{1};'''.format(viConfig.workDir, self.remote.askPass))
			return

		#secondly decide whether the container is exist
		startupScript = self.onStartupCmds()
		if self.isStopped():
			self.guest['status'] = GUEST_STAT_STOPPED
			myprint("exist docker for vivi_%s, need do startup" % self.ip)
			startupScript += self.onRestartCmds()
		
		self.remote.sexe('''
						cd ~/{1};
						{0} ./viDocker.sh vivi_1.1:target vivi_{2};
						{4}
						rm {3};
						'''.format(self.sudo_a, viConfig.workDir, self.ip, self.remote.askPass, startupScript))

class viInstall:
	def __init__(self, remote, guest):
		self.remote = remote
		self.guest = guest
		self.askPass = viPasswdHelper(self.remote)
		self.sudo_a = 'SUDO_ASKPASS=/home/%s/%s sudo -A' % (self.remote.user, self.askPass)
	
	def installCmd(self):
		prefix_length = self.guest.get('prefix_length') or viConfig.DEF_GUEST_PREFIX_LENGTH
		gateway = self.guest.get('gateway') or viConfig.DEF_GUEST_GATEWAY
		cmd = '''{0} ./myinstall --ip={1} --netmask={2} --gateway={3};'''.format(self.sudo_a, self.remote.ip, prefix_length, gateway)
		return cmd

	def run(self):
		self.remote.cp('vivi.zip', '~', show=False)
		self.remote.cp(self.askPass, '~')
		
		self.remote.aexe('''
						unzip -o vivi.zip -d vivi_work;
						cd vivi_work;
						{4}
						'''.format(self.sudo_a, self.remote.ip, self.remote.user, self.askPass, self.installCmd()), show=False)

def install():
	global gcall, gOptions
	for guest in viConfig.guests:
		guestIp = guest.get('ip')
		guestUser = guest.get('user') or viConfig.DEF_GUEST_USER
		guestPasswd = guest.get('passwd') or viConfig.DEF_GUEST_PASSWD
		host = guest.get('host')
		myprint("install guest %s" % (guestIp))
		if host:
			#setup guest firstly
			ip = host
			myprint("setup host %s" % (ip))
			host = viConfig.hosts.get(host)
			user = host.get('user') or viConfig.DEF_HOST_USER
			passwd = host.get('passwd') or viConfig.DEF_HOST_PASSWD
			remote = viRemote(ip, user, passwd, 'vivi_inhost_%s.log' % guestIp)
			
			host = viHost(remote, guestIp)
			host.prepare()
			host.setup()
			myprint("setup host %s: Done" % (ip))
		
		if not gOptions.get('install') and guest.get('status') != GUEST_STAT_NOEXIST:
			myprint("skip install because of guest(%s) %s" % (guest.get('ip'), guest.get('status')))
			continue

		remote = viRemote(guestIp, guestUser, guestPasswd, 'vivi_install_%s.log' % guestIp)
		installer = viInstall(remote, guest)
		installer.run()
		myprint("install guest %s: Done" % (guestIp))
		
	myprint("waiting for install finish")
	gcall.await()

import sys
import getopt
if __name__ == "__main__":
	gcall = mycall()

	# flush all arp entries because the new docker instance will use different MAC address
	gcall.scall('sudo ip neigh flush all')

	install()