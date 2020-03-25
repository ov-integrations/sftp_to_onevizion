import onevizion
import argparse
import pysftp
import re
import time
import paramiko
from datetime import datetime

Description="""Import files from SFTP to OV in order
"""
#EpiLog = onevizion.PasswordExample + """\n\n
#"""
EpiLog = ""
parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,description=Description,epilog=EpiLog)
parser.add_argument("-p", "--passwords", metavar="PasswordsFile", help="JSON file where passwords are stored.", default="Passwords.json")
parser.add_argument("-v", "--verbose", action='count', default=0, help="Print extra debug messages and save to a file. Attach file to email if sent.")
parser.add_argument("-w", "--website", help="website name.")
args = parser.parse_args()
PasswordsFile = args.passwords

parameters = onevizion.GetParameters(PasswordsFile)
onevizion.Config["Verbosity"]=args.verbose
onevizion.Config["SMTPToken"]="SMTP"
Message = onevizion.Message
Trace = onevizion.Config["Trace"]


PDError = (
	onevizion.CheckPasswords(parameters,'SMTP',['Server','Port','UserName','Password','To']),
	",\n",
	onevizion.CheckPasswords(parameters,'SFTP',['Url','UserName','Directory','KeyFile'])
	)
if len(PDError) > 3:
	print (PDError)
	quit()

website = parameters[args.website]
#Message(website)

###### sort a list file names based on imbedded timestamp
def sortalist(listOfFileName,params):
	if len(listOfFileName) == 0:
		return None

	def return_date_from_filename(f):
		p = re.compile(params['dateprefix'])
		r = p.search(f)
		return datetime.strptime(r.group(0).replace(params['datecruft'],''), params['datefmt'])

	if params['datefmt'] is None:
		return listOfFileName
	else:
		return sorted(listOfFileName,key=return_date_from_filename)



###### Run an import and wait for it to complete
def runAndWaitForImport(filename, impspec, action):
	tries = 0

	imp = onevizion.Import(
		userName = website['UserName'],
		password = website['Password'],
		URL = website['url'],
		impSpecId=impspec,
		file=filename,
		action=action,
		comments=filename
		)

	if len(imp.errors)>0:
		return False

	PID = imp.processId

	d = True
	while d:
		time.sleep(5)
		process_data = imp.getProcessData(processId=PID)
		#Message(process_data.jsonData)
		if len(imp.errors)>0:
			#todo - possibly just keep trying
			continue

		if process_data["status"] in ['EXECUTED','EXECUTED_WITHOUT_WARNINGS','EXECUTED_WITH_WARNINGS']:
			d = False

		tries = tries + 1
		if tries>100:
			#todo error handling
			return False

	if process_data["status"] in ['EXECUTED','EXECUTED_WITHOUT_WARNINGS','EXECUTED_WITH_WARNINGS']:
		return True


#####  Main section

class MyCnOpts:
	pass

# connect to SFTP
try:
	#not best practice, but avoids needing entry in .ssh/known_hosts
	#from Joe Cool near end of https://bitbucket.org/dundeemt/pysftp/issues/109/hostkeysexception-no-host-keys-found-even
	cnopts = MyCnOpts()
	cnopts.log = False
	cnopts.compression = False
	cnopts.ciphers = None
	cnopts.hostkeys = None
	sftp = pysftp.Connection(parameters['SFTP']['url'],
		username=parameters['SFTP']['UserName'],
		password=parameters['SFTP']['Password'],
		cnopts = cnopts
		)
except:
	Trace['SFTP Connect'] = sys.exc_info()[0]
	quit(1)


# get complete list of files in directory
with sftp.cd(parameters['SFTP']['Directory']):
	files = sftp.listdir()

#Message(files)
#Message(parameters['SFTP']['Directory'])

# Using order in parameters, run all files for import type
# wait for each trackor type to complete
# then process next trackor type
# The order is based on parent child relationship in tree ensuring parents created first.
for imp in parameters["IMPORT_ORDER"]:

	#Message(parameters["IMPORTS"][imp])
	r = re.compile(parameters["IMPORTS"][imp]["prefix"])
	filteredFiles = sortalist(list(filter(r.match,files)),parameters["IMPORTS"][imp])
	#Message(filteredFiles)
	if filteredFiles is None:
		continue

	for f in filteredFiles:
		Message(f)
		try:
			sftp.get(parameters['SFTP']['Directory']+f, preserve_mtime=True)
		except:
			Message(sys.exc_info)
			quit(1) # process files on next fun.  Error on getting file usually because file is still being written to.

		if runAndWaitForImport(f,parameters["IMPORTS"][imp]["impspec"],parameters["IMPORTS"][imp]["action"]):
			sftp.rename(parameters['SFTP']['Directory']+f,parameters['SFTP']['Directory']+'processed/'+f)
			Message("successfully imported {filename}".format(filename=f))
			#quit()
			continue
		else:
			#TODO error and send email
			break

		try:
			os.remove(f)
		except:
			None
