#!/usr/bin/env python

import docker
import os
import sys
import logging
import logging.handlers
import getopt

logger = None

def printHelp():
	print "Usage: %s [-h|--help] [-o|--outputdir=] <outputdir> [-t|--templatedir=] <tempatedir> [-s|--socket=] <socket> [-l|--logfile=] <logfile>" % sys.argv[0]

def setLogging(options):
	LOG_FILENAME = options['logfile']
	logger = logging.getLogger('generator')
	logger.setLevel(logging.DEBUG)

	handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=1048576, backupCount=5)
	logger.addHandler(handler)

def get_router_virtual_host(detailList):
	env = detailList["Config"]["Env"]
	router_virtual_host = None
	for env_param in env:
		sp = env_param.split('=')
		if sp[0] == 'ROUTER_VIRTUAL_HOST':
			router_virtual_host = sp[1]

	return router_virtual_host

def get_router_virtual_port(detailList):
	env = detailList["Config"]["Env"]
	router_virtual_port = None
	for env_param in env:
		sp = env_param.split('=')
		if sp[0] == 'ROUTER_VIRTUAL_PORT':
			router_virtual_port = sp[1]

	return router_virtual_port

def get_router_virtual_cert(detailList):
	env = detailList["Config"]["Env"]
	router_virtual_cert = None
	for env_param in env:
		sp = env_param.split('=')
		if sp[0] == 'ROUTER_VIRTUAL_CERT':
			router_virtual_cert = sp[1]

	return router_virtual_cert

def get_ip_address(detailList):
	return detailList["NetworkSettings"]["IPAddress"]

def removeOldFiles(dir, generatedFileNames):
	for (_, __, files) in os.walk(dir):
		for file in files:
			if file.startswith('generated.'):
				fullPathFile = '%s/%s' % (dir, file)
				if not fullPathFile in generatedFileNames:
					logger.debug('Removing old file %s' % fullPathFile)
					os.remove(fullPathFile)

def writeFile(filePath, output):
	outputFile = open(filePath, 'w+')
	outputFile.write(output)
	outputFile.close()
	logger.debug('Add new file %s' % filePath)

def generateTemplate(templateFile, filePath, host_name, host_ip, host_cert, host_port):
	# Load template and fill with data
	templateFile = open(templateFile,'r')
	output = templateFile.read() % ( { "hostname": host_name, "ipaddress": host_ip, "cert": host_cert, "port": host_port    } )

	# Check if file exists, if there are no changes, do nothing (We want to detect changes later on to reload nginx)
	if os.path.isfile(filePath):
		existingFile = open(filePath, 'r')
		fileContent = existingFile.read()
		if fileContent != output:
			writeFile(filePath, output)
	else:
		writeFile(filePath, output)


def main(argv):
	options = getOptions(argv)

	if options['help']:
		printHelp()
		exit(0)

	setLogger(options)

	c = docker.Client(base_url=options['socket'],
			  version='1.12',
			  timeout=10)

	containerList = c.containers(quiet=False, all=False, trunc=True, latest=False, since=None,
		     before=None, limit=-1)

	generatedFileNames = []

	for container in containerList:
		detailList = c.inspect_container(container["Id"])

		host_ip = get_ip_address(detailList)
		host_name = get_router_virtual_host(detailList)
		host_cert = get_router_virtual_cert(detailList)
		host_port = get_router_virtual_port(detailList)

		logger.debug('Handling container IP %s & VHost %s' % ( host_ip, host_name ))

		if host_name and host_name.startswith('www.'):
			host_name = host_name[4:]

		# Check if the mimimum is set
		if host_ip and host_name:
			filePath = '%s/generated.%s.conf' % (options['outputdir'], host_name)
			generateTemplate('%s/nginx.conf.tpl' % options['templatedir'], filePath, host_name, host_ip, host_cert, host_port)
			generatedFileNames.append(filePath)

			filePath = '%s/generated.redirect.%s.conf' % (options['outputdir'], host_name)
			generateTemplate('%s/redirect.nginx.conf.tpl' % options['templatedir'], filePath, host_name, host_ip, host_cert, host_port)
			generatedFileNames.append(filePath)

	removeOldFiles(options['outputdir'], generatedFileNames)

def getOptions(argv):
	getopts, remainder = getopt.getopt(argv, "o:t:s:l:h", [
		'outputdir=',
		'templatedir=',
		'socket=',
		'logfile=',
		'help'
	])

	options = {
		'outputdir': 'output',
		'templatedir': 'template',
		'socket': 'unix://var/run/docker.sock',
		'logfile': 'generator.log',
		'help': False
	}

	for opt, arg in getopts:
		if opt in ('-o', '--outputdir'):
			options['outputdir'] = arg.strip('/')
		elif opt in ('-t', '--templatedir'):
			options['templatedir'] = arg.strip('/')
		elif opt in ('-s', '--socket'):
			options['socket'] = arg
		elif opt in ('-l', '--logfile'):
			options['logfile'] = arg
		elif opt in ('-h', '--help'):
			options['help'] = True

	return options

if __name__ == "__main__":
	main(sys.argv[1:])
