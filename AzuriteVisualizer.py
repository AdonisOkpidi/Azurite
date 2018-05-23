#!/usr/bin/env python
# encoding: UTF-8

import json
from pprint import pprint
import datetime
import re
import sys

def parseJson():
	''' Main application logic of parser. Parses the JSON file which contains the Azure subscription configuration and
	it was generated by the Azurite Explorer. Converts the file to a JSON object that is understoon by the AzuriteVisualizer.html
	in order to create the Graph representation of the Azure resources.

	Operates on the JSON input file provided by the user in the command line.
	'''

	if not len(sys.argv) > 1:
		print "[!] Please provide input file. (Hint: Azurite Explorer output for Azure Subscription.)"
		print "[!] Usage: python AzuriteVisualizer.py <json_file>"
		sys.exit()

	# PowerShell generates the output in UTF-8 with BOM.
	#Convert to UTF-8 to be understoon by the json module.
	inputFile = open(sys.argv[1])
	jsonIn = inputFile.read()
	unicodeJsonIn = jsonIn.decode("utf-8-sig")
	jsonIn = unicodeJsonIn.encode("utf-8")

	# Load the JSON object as string.
	data = json.loads(jsonIn)

	# Initialise variable for the id of the nodes in the final JSON object.
	id = 0

	print "[*] Parsing data..."
	# Initialise the final JSON object.
	jsonOut = {"type": "NetworkGraph", "label": "Azure Subscription Configuration", "nodes": [], "links": []}

	# For each JSON array iterate through the values and after each step that is completed,
	# append the retrieved information in final JSON object.
	#print(type(data['subscriptionVNETs']))
	for vnet in data['subscriptionVNETs']:
		#Iterate through the Virtual Network properties.
		vnetNode = {}
		vnetProperties = {}
		vnetSourceNode = {}
		#print("Here is vnet")
		#print(data['subscriptionVNETs']['vnetName'])

		# Create the main values for the node.
		id, vnetNode['id'] = id + 1, id
		vnetProperties['nodeType'] = 'vnet'
		#vnetNode['label'] = vnet['vnetName']
		vnetNode['label'] = data['subscriptionVNETs']['vnetName']

		# Create the values for the node's properties.
		vnetProperties['location'] = data['subscriptionVNETs']['vnetLocation']
		vnetProperties['vnetAddressSpace'] = ', '.join(data['subscriptionVNETs']['vnetAddressSpaces']['AddressPrefixes'])

		vnetNode['properties'] = vnetProperties
		jsonOut['nodes'].append(vnetNode)

		for subnet in data['subscriptionVNETs']['vnetSubnets']:
			# Iterate through the Virtual Network's subnet properties.
			subnetNode = {}
			subnetProperties = {}
			subnetSourceNode = {}
			subnetDestinationNode = {}
			subnetToVnetLink = {}
			subnetToVnetLinkProperties = {}
			subnetNetworkSecurityGroupsStatus = 'OK'

			# Create the main values for the node.
			id, subnetNode['id'] = id + 1, id
			subnetProperties['nodeType'] = 'subnet'
			subnetNode['label'] = subnet['subnetName']

			# Create the values for the node's properties.
			subnetProperties['subnetAddressSpace'] = subnet['subnetAddressSpace']
			subnetProperties['vnetName'] = data['subscriptionVNETs']['vnetName']

			# Parse the subnet's Network Security Groups (NSGs) and retrieve the weak NSG rules.
			# Gateway Subnet cannot have NSGs.
			if subnet['subnetName'] != 'GatewaySubnet':
				if subnet['subnetNetworkSecurityGroups']:

					# Check the configuration of the Subnet's NSGs.
					subnetWeakCustomNetworkSecurityGroups = parseNetworkSecurityGroups(subnet['subnetNetworkSecurityGroups'])

					if subnetWeakCustomNetworkSecurityGroups:
						# Ammend the node's properties in case weak NSGs were identified.
						subnetProperties['nodeType'] = 'subnet-weak-nsg'
						subnetProperties['weakNetworkSecurityGroupsCustomRules'] = ', '.join(subnetWeakCustomNetworkSecurityGroups)
						subnetNetworkSecurityGroupsStatus = 'Weak'
				else:
					subnetProperties['nodeType'] = 'subnet-weak-nsg'
					subnetProperties['weakNetworkSecurityGroupsCustomRules'] = 'Not defined'
					subnetNetworkSecurityGroupsStatus = 'Weak'


			subnetNode['properties'] = subnetProperties


			jsonOut['nodes'].append(subnetNode)

			# Add link for each Subnet - Source is subnet, Destination is VNet.
			# Cost is always 1.
			subnetToVnetLink['source'] = subnetNode['id']
			subnetToVnetLink['target'] = vnetNode['id']
			subnetToVnetLink['cost'] = 1

			# Add link properties to determine the connection between the nodes.
			subnetToVnetLinkProperties['linkType'] = 'subnet-to-vnet'
			subnetToVnetLink['properties'] = subnetToVnetLinkProperties

			jsonOut['links'].append(subnetToVnetLink)

			if 'subnetItems' in subnet:
				# Iterate through the Subnet's items (VMs or VNet Gateways).
				for subnetItem in subnet['subnetItems']:
					subnetItemNode = {}
					subnetItemProperties = {}
					vmPrivateIpAddresses = []
					vmPublicIpAddresses = []

					id, subnetItemNode['id'] = id + 1, id
					if (subnetItem['itemType'] == 'Virtual Machine'):
						vmToSubnetLink = {}
						vmToSubnetLinkProperties = {}

						subnetItemNode['label'] = subnetItem['vmName']

						# Populate node's properties.
						# Get the VM's private and public IP configuration.
						for vmNetworkIpConfiguration in subnetItem['vmNetworkConfiguration']['vmNetworkConfigurationIpConfigurations']:

							vmPrivateIpAddresses.append(vmNetworkIpConfiguration['vmNetworkConfigurationPrivateIpAddress'] + ' (' + vmNetworkIpConfiguration['vmNetworkConfigurationName'] + ')')

							if 'vmNetworkConfigurationPublicIpAddress' in vmNetworkIpConfiguration:
								vmPublicIpAddresses.append(vmNetworkIpConfiguration['vmNetworkConfigurationPublicIpAddress'] + ' (' + vmNetworkIpConfiguration['vmNetworkConfigurationName'] + ')')

						subnetItemProperties['privateIpAddress'] = ', '.join(vmPrivateIpAddresses)
						if vmPublicIpAddresses:
							subnetItemProperties['publicIpAddress'] = ', '.join(vmPublicIpAddresses)
						subnetItemProperties['vnetName'] = data['subscriptionVNETs']['vnetName']
						subnetItemProperties['subnetName'] = subnet['subnetName']
						subnetItemProperties['vmOsEncrypted'] = subnetItem['vmEncryption']['osVolumeEncryption']
						subnetItemProperties['vmDiskEncrypted'] = subnetItem['vmEncryption']['dataVolumesEncryption']
						subnetItemProperties['nodeType'] = 'vm'

						# Parse the VM's Network Security Groups (NSGs) and retrieve the weak NSG rules.
						if subnetItem['vmNetworkSecurityGroups']:
							vmWeakCustomNetworkSecurityGroups = parseNetworkSecurityGroups(subnetItem['vmNetworkSecurityGroups'], subnetNetworkSecurityGroupsStatus)
							if vmWeakCustomNetworkSecurityGroups:
								# Ammend the node's properties in case weak NSGs were identified.
								subnetItemProperties['nodeType'] = 'vm-weak-nsg'
								subnetItemProperties['weakNetworkSecurityGroupsCustomRules'] = ', '.join(vmWeakCustomNetworkSecurityGroups)
						else:
							subnetItemProperties['nodeType'] = 'vm-weak-nsg'
							subnetItemProperties['weakNetworkSecurityGroupsCustomRules'] = "Not defined"

						subnetItemNode['properties'] = subnetItemProperties

						jsonOut['nodes'].append(subnetItemNode)

						# Add link for each VM - Source is VM, Destination is the Subnet.
						vmToSubnetLink['source'] = subnetItemNode['id']
						vmToSubnetLink['target'] = subnetNode['id']
						vmToSubnetLink['cost'] = 1

						# Add link properties to determine the connection between the nodes.
						vmToSubnetLinkProperties['linkType'] = 'vm-to-subnet'
						vmToSubnetLink['properties'] = vmToSubnetLinkProperties


						jsonOut['links'].append(vmToSubnetLink)
					else:
						gatewayToSubnetLink = {}
						gatewayToSubnetLinkProperties = {}

						subnetItemNode['label'] = subnetItem['virtualNetworkGatewayName']

						# Populate node's properties.
						subnetItemProperties['publicIpAddress'] = subnetItem['virtualNetworkGatewayNetworkConfiguration']['virtualNetworkGatewayPublicIpAddress']
						# subnetItemProperties['privateIpAddress'] = subnetItem['virtualNetworkGatewayNetworkConfiguration']['virtualNetworkGatewayPrivateIpAddress']
						subnetItemProperties['nodeType'] = 'gateway'

						subnetItemProperties['vnetName'] = vnet['vnetName']
						subnetItemProperties['subnetName'] = subnet['subnetName']


						subnetItemNode['properties'] = subnetItemProperties
						jsonOut['nodes'].append(subnetItemNode)

						# Add link for each Gateway - Source is the Gateway, Destination is the Subnet.
						gatewayToSubnetLink['source'] = subnetItemNode['id']
						gatewayToSubnetLink['target'] = subnetNode['id']
						gatewayToSubnetLink['cost'] = 1

						# Add link properties to determine the connection between the nodes.
						gatewayToSubnetLinkProperties['linkType'] = 'gateway-to-subnet'
						gatewayToSubnetLink['properties'] = gatewayToSubnetLinkProperties

						jsonOut['links'].append(gatewayToSubnetLink)

	if 'subscriptionLocalNetworkGateways' in data:
		# Iterate through the Local Network Gateway properties.
		for localNetworkGateway in data['subscriptionLocalNetworkGateways']:
			localNetworkGatewayNode = {}
			localNetworkGatewayProperties = {}

			id, localNetworkGatewayNode['id'] = id + 1, id

			# Populate node's properties.
			localNetworkGatewayNode['nodeType'] = 'local-network-gateway'
			localNetworkGatewayNode['label'] = localNetworkGateway['localNetworkGatewayName']
			localNetworkGatewayProperties['nodeType'] = 'gateway'

			localNetworkGatewayProperties['localGatewayAddressSpace'] = ', '.join(localNetworkGateway['localNetworkGatewayNetworkConfiguration']['localNetworkGatewayAddressSpace'])
			localNetworkGatewayProperties['localGatewayPubliIpAddress'] = localNetworkGateway['localNetworkGatewayNetworkConfiguration']['localNetworkGatewayPublicIpAddress']

			localNetworkGatewayNode['properties'] = localNetworkGatewayProperties

			jsonOut['nodes'].append(localNetworkGatewayNode)

	if 'subscriptionSqlServers' in data:
		# Iterate through the Azure SQL Server properties.
		for sqlServer in data['subscriptionSqlServers']:
			sqlServerNode = {}
			sqlServerProperties = {}

			id, sqlServerNode['id'] = id + 1, id

			# Populate node's properties.
			sqlServerNode['nodeType'] = 'azure-sql-server'
			sqlServerNode['label'] = sqlServer['sqlServerName']

			sqlServerProperties['sqlServerVersion'] = sqlServer['sqlServerVersion']
			sqlServerProperties['location'] = sqlServer['sqlServerLocation']

			# TODO: Retrieve audit state from the cmdlet and represent in human readable format.
			sqlServerProperties['auditState'] = sqlServer['sqlServerAuditingPolicy']['AuditState']

			# Retrieve the SQL Server's firewall rules.
			sqlServerFirewallRules = []
			for sqlServerFirewallRule in sqlServer['sqlServerFirewallRules']:
				if sqlServerFirewallRule['StartIpAddress'] == sqlServerFirewallRule['EndIpAddress']:
					sqlServerFirewallRules.append(sqlServerFirewallRule['StartIpAddress'] + " (" + sqlServerFirewallRule['FirewallRuleName'] + ")")
				else:
					sqlServerFirewallRules.append(sqlServerFirewallRule['StartIpAddress'] + "-" + sqlServerFirewallRule['EndIpAddress'] + " (" + sqlServerFirewallRule['FirewallRuleName'] + ")")

			sqlServerProperties['sqlServerFirewallRules'] = ', '.join(sqlServerFirewallRules)

			sqlServerNode['properties'] = sqlServerProperties
			jsonOut['nodes'].append(sqlServerNode)


			if 'sqlServerDatabases' in sqlServer:
				# Iterate through the properties of the Azure SQL Databases that are hosted on the Azure SQL Server.
				for sqlServerDatabase in sqlServer['sqlServerDatabases']:
			 		sqlServerDatabaseNode = {}
					sqlServerDatabaseProperties = {}
					azureSqlDatabaseToazureSqlServerLink = {}
					azureSqlDatabaseToazureSqlServerLinkProperties = {}

					id, sqlServerDatabaseNode['id'] = id + 1, id

					# Populate node's properties.
					sqlServerDatabaseNode['label'] = sqlServerDatabase['sqlDatabaseName']

					sqlServerDatabaseProperties['location'] = sqlServerDatabase['sqlDatabaseLocation']
					sqlServerDatabaseProperties['sqlDatabaseServerName'] = sqlServerDatabase['sqlDatabaseServerName']
					sqlServerDatabaseProperties['nodeType'] = 'azure-sql-database'
					sqlServerDatabaseProperties['auditState'] = sqlServerDatabase['sqlDatabaseAuditingPolicy']['AuditState']

					# Retrieve the Azure SQL Database's data masking policy.
					if 'sqlDatabaseDataMaskingPolicy' in sqlServerDatabase:
						sqlServerDatabaseProperties['dataMaskingState'] = sqlServerDatabase['sqlDatabaseDataMaskingPolicy']['DataMaskingState']

					sqlServerDatabaseProperties['ProxyDnsName'] = sqlServerDatabase['sqlDatabaseSecureConnectionPolicy']['ProxyDnsName']
					sqlServerDatabaseProperties['ProxyPort'] = sqlServerDatabase['sqlDatabaseSecureConnectionPolicy']['ProxyPort']
					sqlServerDatabaseProperties['ConnectionStrings'] = str(sqlServerDatabase['sqlDatabaseSecureConnectionPolicy']['ConnectionStrings'])
					sqlServerDatabaseProperties['transparentDataEncryption'] = sqlServerDatabase['sqlDatabaseTransparentDataEncryption']

					sqlServerDatabaseNode['properties'] = sqlServerDatabaseProperties
					jsonOut['nodes'].append(sqlServerDatabaseNode)

					# Add link for each Azure SQL Database - Source is the Azure SQL Database, Destination is the Azure SQL Server.
					azureSqlDatabaseToazureSqlServerLink['source'] = sqlServerDatabaseNode['id']
					azureSqlDatabaseToazureSqlServerLink['target'] = sqlServerNode['id']
					azureSqlDatabaseToazureSqlServerLink['cost'] = 1

					# Add link properties to determine the connection between the nodes.
					azureSqlDatabaseToazureSqlServerLinkProperties['linkType'] = 'azure-sql-database-to-azure-sql-server'
					azureSqlDatabaseToazureSqlServerLink['properties'] = azureSqlDatabaseToazureSqlServerLinkProperties

					jsonOut['links'].append(azureSqlDatabaseToazureSqlServerLink)

	if 'subscriptionWebApps' in data:
		# Iterate through the Azure Web Application's properties.
		for webApp in data['subscriptionWebApps']:

			webAppNode = {}
			webAppProperties = {}

			id, webAppNode['id'] = id + 1, id

			# Populate node's properties.
			webAppNode['nodeType'] = 'web-app'
			webAppNode['label'] = webApp['webAppName']

			webAppProperties['webAppResourceGroupName'] = webApp['webAppResourceGroupName']
			webAppProperties['location'] = webApp['webAppLocation']
			webAppProperties['webAppHostNames'] = webApp['webAppHostNames']
			webAppProperties['webAppOutboundIpAddresses'] = webApp['webAppOutboundIpAddresses']

			# Retrieve Azure Web Application's SSL/TLS configuration.
			if 'webAppSSLCertificate' in webApp:
				webAppProperties['webAppSSLCertificateName'] = webApp['webAppSSLCertificate']['webAppSSLCertificateName']
				webAppProperties['webAppSSLCertificateSubjectName'] = webApp['webAppSSLCertificate']['webAppSSLCertificateSubjectName']
				webAppProperties['webAppSSLCertificateIssuer'] = webApp['webAppSSLCertificate']['webAppSSLCertificateIssuer']

				# Calculate the expiration date from the timestamp returned from the Azure PowerShell cmdlet.
				webAppProperties['webAppSSLCertificateExpirationDate'] = str(datetime.datetime.fromtimestamp(int(re.findall('\d+', str(webApp['webAppSSLCertificate']['webAppSSLCertificateExpirationDate']))[0].encode('ascii')[:10])))
			webAppNode['properties'] = webAppProperties
			jsonOut['nodes'].append(webAppNode)

	# Function call to create the connections between the Gateways in the subscription (if any);
	# It performs the connections: VNet Gateway-to-VNet Gateway and VNet Gateway-to-Local Network Gateway.
	jsonOut = connectGatewaysToGateways(data, jsonOut)

	# Create the final JSON object.
	jsonOutRaw = json.dumps(jsonOut)
	print "[+] The following JSON object was generated:\n"
	print jsonOutRaw

	# Export the final JSON object and save it to a file.
	jsonOutFile = open('azure-subscription-nodes.json', 'w')
	jsonOutFile.write(json.dumps(jsonOut, sort_keys=True, indent=4))
	jsonOutFile.close()

	print "\n\n"
	print "[*] Output was saved in the file: azure-subscription-nodes.json"
	print "[*] Please proceed to open the AzuriteVisualizer.html in Firefox to view the Graph."

def parseNetworkSecurityGroups(jsonNetworkSecurityGroups, subnetNetworkSecurityGroupCustomRulesStatus = 'OK'):
	''' Parse the Network Security Groups (NSGs) for Subnets and Virtual Machines.
	For each weak NSG that is identified append to an array that is returned to the function call.

	Currently only basic business logic to retrieve the weak NSGs is supported. The following rules are used:

	* Direction - Inbound:
		- Source port range is 'ALL' (*) and Destination port range includes ports of the Management Interfaces.
		- Source IP address range 'ALL' (*) and Destination IP address range is 'ALL' (*)
		- Destination port range is 'ALL' (*)
	* Direction - Outbound:
		- Source IP address range 'ALL' (*) and Destination IP address range is 'ALL' (*)
		- Destination port range is 'ALL' (*)

	Attributes:
		jsonNetworkSecurityGroups: A JSON object of the NSGs of either a Subnet or a VM.
		subnetNetworkSecurityGroupCustomRulesStatus: This is used when the function is called for the NSGs of a VM.
			The attribute refers to the state of the NSG rules for the associated Subnet. This is used to determine whether the Subnet is secure or not.
			If the Subnet is not secure further parsing will be performed to determine the status of the NSG rules for the VM.
	'''


	nsgWeakRules = []
	nsgWeakCustomRules = []

	# Array to define weak protocols.
	clearTextProtocols = [21, 23, 69, 512, 512, 513, 514]

	# Array to define management ports.
	managementPorts = [21, 22, 23, 161, 3389, 512, 513, 514, 1433, 3306, 1521, 4321]

	# Check the NSGs for the Subnet.
	if 'subnetNetworkSecurityGroupCustomRules' in jsonNetworkSecurityGroups:
		for subnetNetworkSecurityGroupCustomRule in jsonNetworkSecurityGroups['subnetNetworkSecurityGroupCustomRules']:
			# Only the NSG rules that have been successfuly provisioned are reviewed.
			if subnetNetworkSecurityGroupCustomRule['ProvisioningState'] == 'Succeeded':
				if subnetNetworkSecurityGroupCustomRule['Direction'] == 'Inbound' and subnetNetworkSecurityGroupCustomRule['Access'] == 'Allow' and (((subnetNetworkSecurityGroupCustomRule['DestinationPortRange'] in managementPorts) and subnetNetworkSecurityGroupCustomRule['SourcePortRange'] == '*') or (subnetNetworkSecurityGroupCustomRule['SourceAddressPrefix'] == '*' and subnetNetworkSecurityGroupCustomRule['DestinationAddressPrefix'] == '*') or (subnetNetworkSecurityGroupCustomRule['DestinationPortRange'] == '*')):
					nsgWeakCustomRules.append(subnetNetworkSecurityGroupCustomRule['Direction'] + "-" + subnetNetworkSecurityGroupCustomRule['Name'])
				elif subnetNetworkSecurityGroupCustomRule['Direction'] == 'Outbound' and subnetNetworkSecurityGroupCustomRule['Access'] == 'Allow' and ((subnetNetworkSecurityGroupCustomRule['SourceAddressPrefix'] == '*' and subnetNetworkSecurityGroupCustomRule['DestinationAddressPrefix'] == '*') or (subnetNetworkSecurityGroupCustomRule['DestinationPortRange'] == '*')):
					nsgWeakCustomRules.append(subnetNetworkSecurityGroupCustomRule['Direction'] + "-" + subnetNetworkSecurityGroupCustomRule['Name'])

	# In case the NSGs for the Subnet of the associated VM are weak, perform checks on the VM's NSGs.
	# Otherwise the perimeter is considered secure.
	if subnetNetworkSecurityGroupCustomRulesStatus == 'Weak' and 'vmNICNetworkSecurityGroupCustomRules' in jsonNetworkSecurityGroups:
		for vmNetworkSecurityGroupCustomRule in jsonNetworkSecurityGroups['vmNICNetworkSecurityGroupCustomRules']:
			# Only the NSG rules that have been successfuly provisioned are reviewed.
			if vmNetworkSecurityGroupCustomRule['ProvisioningState'] == 'Succeeded':
				if vmNetworkSecurityGroupCustomRule['Direction'] == 'Inbound' and vmNetworkSecurityGroupCustomRule['Access'] == 'Allow' and (
					(vmNetworkSecurityGroupCustomRule['DestinationPortRange'] in managementPorts) or (vmNetworkSecurityGroupCustomRule['SourceAddressPrefix'] == '*' and vmNetworkSecurityGroupCustomRule['DestinationAddressPrefix'] == '*') or (vmNetworkSecurityGroupCustomRule['DestinationPortRange'] == '*')):
						nsgWeakCustomRules.append(vmNetworkSecurityGroupCustomRule['Direction'] + "-" + vmNetworkSecurityGroupCustomRule['Name'])
				elif vmNetworkSecurityGroupCustomRule['Direction'] == 'Outbound' and vmNetworkSecurityGroupCustomRule['Access'] == 'Allow' and ((vmNetworkSecurityGroupCustomRule['SourceAddressPrefix'] == '*' and vmNetworkSecurityGroupCustomRule['DestinationAddressPrefix'] == '*') or (vmNetworkSecurityGroupCustomRule['DestinationPortRange'] == '*')):
					nsgWeakCustomRules.append(vmNetworkSecurityGroupCustomRule['Direction'] + "-" + vmNetworkSecurityGroupCustomRule['Name'])

	return nsgWeakCustomRules

def connectGatewaysToGateways(jsonData, jsonOut):
	''' Function to create nodes and links for the connections between the Azure Gateways,
	VNet Gateway-to-VNet Gateway and VNet Gateway-to-Local Network Gateway.

	Attributes:
		jsonData: The original JSON object.
		jsonOut: A JSON object including only the links (connections) between the Gateways discovered in the network.
	'''

	# Iterate through the subscription components to identify the connections between the Gateways.
	for vnet in jsonData['subscriptionVNETs']:
		for subnet in jsonData['subscriptionVNETs']['vnetSubnets']:
			if 'subnetItems' in subnet:
				for subnetItem in subnet['subnetItems']:
					if (subnetItem['itemType'] == 'Virtual Network Gateway'):
							# Add a link for each VNet Gateway to VNet Gateway connection.
							if 'virtualNetworkGatewayConnections' in subnetItem:
								vnetGatewayToVnetGatewayLink = {}
								vnetGatewayToVnetGatewayLinkProperties = {}

								# Retrieve the source and destination for the connection.
								sourceId = next(id for (id, d) in enumerate(jsonOut['nodes']) if
									d["label"] == subnetItem['virtualNetworkGatewayConnections']['virtualNetworkGatewayConnectionGateway1'])
								targetId = next(id for (id, d) in enumerate(jsonOut['nodes']) if
									d["label"] == subnetItem['virtualNetworkGatewayConnections']['virtualNetworkGatewayConnectionGateway2'])

								# Check for bidirectional connections.
								for d in jsonOut['links']:
									if d.get("source") == sourceId and d.get("target") == targetId or d.get("source") == targetId and d.get("target") == sourceId:
										vnetGatewayToVnetGatewayLinkProperties['Bidirectional'] = 'True'
										vnetGatewayToVnetGatewayLinkProperties['Complementary connection name'] = d.get("properties").get("connectionName")

								# Add link for each Gateway to Gateway connection.
								vnetGatewayToVnetGatewayLink['source'] = sourceId
								vnetGatewayToVnetGatewayLink['target'] = targetId
								vnetGatewayToVnetGatewayLink['cost'] = 1

								# Add link properties to determine the connection between the nodes.
								vnetGatewayToVnetGatewayLinkProperties['linkType'] = 'vnet-gateway-to-vnet-gateway'
								vnetGatewayToVnetGatewayLinkProperties['connectionName'] = subnetItem['virtualNetworkGatewayConnections']['virtualNetworkGatewayConnectionName']
								vnetGatewayToVnetGatewayLink['properties'] = vnetGatewayToVnetGatewayLinkProperties
								jsonOut['links'].append(vnetGatewayToVnetGatewayLink)

	return jsonOut


def banner():
	''' Function to print the tool's banner and various details.
	'''
	logo = """
 █████  ███████╗██╗   ██╗██████╗ ██╗████████╗███████╗
██╔══██╗╚══███╔╝██║   ██║██╔══██╗██║╚══██╔══╝██╔════╝
███████║  ███╔╝ ██║   ██║██████╔╝██║   ██║   █████╗
██╔══██║ ███╔╝  ██║   ██║██╔══██╗██║   ██║   ██╔══╝
██║  ██║███████╗╚██████╔╝██║  ██║██║   ██║   ███████╗
╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝   ╚═╝   ╚══════╝

            ██╗   ██╗██╗███████╗██╗   ██╗ █████╗ ██╗     ██╗███████╗███████╗██████╗
            ██║   ██║██║██╔════╝██║   ██║██╔══██╗██║     ██║╚══███╔╝██╔════╝██╔══██╗
            ██║   ██║██║███████╗██║   ██║███████║██║     ██║  ███╔╝ █████╗  ██████╔╝
            ╚██╗ ██╔╝██║╚════██║██║   ██║██╔══██║██║     ██║ ███╔╝  ██╔══╝  ██╔══██╗
             ╚████╔╝ ██║███████║╚██████╔╝██║  ██║███████╗██║███████╗███████╗██║  ██║
              ╚═══╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝╚══════╝╚══════╝╚═╝  ╚═╝

Version: 0.6 Beta
Author: Apostolos Mastoris (@Lgrec0)
Email: apostolis.mastoris[at]mwrinfosecurity.com

"""
	print logo


def main():
	''' Main function.
	Perform required function calls.
	'''

	banner()
	parseJson()

if __name__ == '__main__':
    main()
