CREATE OR REPLACE PROCEDURE   load_from_sftp2
        (stage_name string, stage_dir string, sftp_remote_path string, pattern string, sftp_server string ,port integer )
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = 3.8
HANDLER = 'getfiles'
EXTERNAL_ACCESS_INTEGRATIONS = (sftp_aws_ext_int)
PACKAGES = ('snowflake-snowpark-python','paramiko','re2')
SECRETS = ('cred' = sftp_aws_cred)
AS
$$
import _snowflake
import paramiko
import re
import os
import sys
from datetime import datetime
from snowflake.snowpark.files import SnowflakeFile
def getfiles(session, internal_stage, stage_dir,   remote_file_path, pattern, sftp_server, port):
    sftp_cred = _snowflake.get_username_password('cred');
    sftp_host = sftp_server
    sftp_port = port
    sftp_username = sftp_cred.username
    sftp_privatekey = sftp_cred.password
    privkeyfile = '/tmp/content' + str(os.getpid())
    with open(privkeyfile, "w") as file:
      file.write(sftp_privatekey)
    full_path_name = f'{internal_stage}/{stage_dir}'
    #cnopts = pysftp.CnOpts()
    #cnopts.hostkeys = None      
    k = paramiko.RSAKey.from_private_key_file(privkeyfile)
    sftpclient = paramiko.SSHClient()
    sftpclient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sftpclient.connect(hostname=sftp_host, username=sftp_username, pkey=k, port=sftp_port)
    try:
        with  sftpclient.open_sftp() as sftp:    
            #if sftp.exists(remote_file_path):
                sftp.chdir(remote_file_path)
                rdir=sftp.listdir()  
                ret=[]
                for file in (rdir):
                    if re.search(pattern,file) != None:
                        sftp.get(file, f'/tmp/{file}')  
                        session.file.put(f'/tmp/{file}', full_path_name )
                        ret.append(file)
        return ret
    except Exception as e:
        return f" Error with SFTP : {e}"
$$;    

CALL load_from_sftp2('@demodb.demo.demo_stage',
                    'sftpdir','','nyc',
                    's-5efc0c2e810645c7b.server.transfer.us-west-2.amazonaws.com',22);
