import os.path
import os

import cherrypy
import time
import glob
import json
import urllib
import socket
from cherrypy.lib import static
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
import file_operations

def get_immediate_subdirectories(dir) :
    return [name for name in os.listdir(dir)
            if os.path.isdir(os.path.join(dir, name))]

config = { '/':
        {
 		'tools.staticdir.on': True,
		'tools.staticdir.dir': current_dir + '/static/',
		'tools.staticdir.index': 'index.html',
		'tools.encode.on': True,
		'tools.encode.encoding': 'utf-8',
        }
}
#base = '/'
#name = 'File Manager'

class Root():

    def tester(self, name):
        return b"TESTdf"
        print ("cool")
    tester.exposed = True

    def media(self, fpath, cb):
        cherrypy.response.headers['Cache-Control'] = "no-cache, no-store, must-revalidate"
        cherrypy.response.headers['Pragma'] = "no-cache"
        cherrypy.response.headers['Expires'] = "0"
        src = file_operations.BASE_DIR + fpath
        return static.serve_file(src)
    media.exposed = True

    def download(self, fpath, cb):
        src = file_operations.BASE_DIR + fpath
        dl = open(src, 'rb').read()
        fname = os.path.basename(fpath)
        cherrypy.response.headers['content-type']        = 'application/octet-stream'
        cherrypy.response.headers['content-disposition'] = 'attachment; filename={}'.format(fname)
        return dl
    download.exposed = True

    def upload(self, dst, **fdata):
        upload = fdata['files[]']
        folder = dst
        filename = upload.filename
        size = 0
        filepath = file_operations.BASE_DIR + folder + '/' + filename 
        filepath = file_operations.check_and_inc_name(filepath)
        with open(filepath, 'wb') as newfile:
            while True:
                data = upload.file.read(8192)
                if not data:
                    break
                size += len(data)
                newfile.write(data)
        print ("saved file, size: " + str(size))
        # check if it was a zip, unzip and delete orig if so
        p, ext = os.path.splitext(filepath)
        #if ext == ".zip" :
            #print ("that was a zip, gonna unzip")
            #zip_path = filepath
            #zip_parent_folder =os.path.dirname(zip_path)
            #os.system("unzip -o \""+zip_path+"\" -d \""+zip_parent_folder+"\" -x '__MACOSX/*'")
            #os.remove(zip_path)
        
        cherrypy.response.headers['Content-Type'] = "application/json"
        return ('{"files":[{"name":"x","size":'+str(size)+',"url":"na","thumbnailUrl":"na","deleteUrl":"na","deleteType":"DELETE"}]}').encode('utf-8')
        
    upload.exposed = True
  
    def fmdata(self, **data):
        
        ret = ''
        if 'operation' in data :
            cherrypy.response.headers['Content-Type'] = "application/json"
            result = None
            if data['operation'] == 'set_base_dir' :
                result = file_operations.set_base_dir(data['path'])
            if data['operation'] == 'get_node' :
                result = file_operations.get_node(data['path'])
            if data['operation'] == 'create_node' :
                result = file_operations.create(data['path'], data['name'])
            if data['operation'] == 'rename_node' :
                result = file_operations.rename(data['path'], data['name'])
            if data['operation'] == 'delete_node' :
                result = file_operations.delete(data['path'])
            if data['operation'] == 'move_node' :
                result = file_operations.move(data['src'], data['dst'])
            if data['operation'] == 'copy_node' :
                result = file_operations.copy(data['src'], data['dst'])
            if data['operation'] == 'unzip_node' :
                result = file_operations.unzip(data['path'])
            if data['operation'] == 'download_node' :
                result = file_operations.download(data['path'])
            if data['operation'] == 'zip_node' :
                result = file_operations.zip(data['path'])
            if data['operation'] == 'mount_usb' :
                result = file_operations.mountUSB()
            if data['operation'] == 'unmount_usb' :
                result = file_operations.unmountUSB()
            if result is not None:
                return result.encode('utf-8') if isinstance(result, str) else result
              
        else :
            cherrypy.response.headers['Content-Type'] = "application/json"
            return b"no operation specified"

    fmdata.exposed = True

cherrypy.config.update({
    'server.socket_host': '0.0.0.0',
    'server.socket_port': 80,
    'tools.encode.on': True,
    'tools.encode.encoding': 'utf-8',
})
cherrypy.quickstart(Root(), config=config)

