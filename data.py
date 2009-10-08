# -*- coding: utf-8 -*-

##    This file is part of Gertrude.
##
##    Gertrude is free software; you can redistribute it and/or modify
##    it under the terms of the GNU General Public License as published by
##    the Free Software Foundation; either version 3 of the License, or
##    (at your option) any later version.
##
##    Gertrude is distributed in the hope that it will be useful,
##    but WITHOUT ANY WARRANTY; without even the implied warranty of
##    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##    GNU General Public License for more details.
##
##    You should have received a copy of the GNU General Public License
##    along with Gertrude; if not, see <http://www.gnu.org/licenses/>.

import __builtin__
import os.path, shutil, time
import urllib2, mimetypes
import ConfigParser
import sqlinterface
from functions import *

BACKUPS_DIRECTORY = './backups'

TOKEN_FILENAME = '.token'

class HttpConnection(object):
    def __init__(self, url, identity, auth_info=None, proxy_info=None):
        self.url = url
        self.identity = identity
        opener = urllib2.build_opener()
        if auth_info:
            password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
            password_mgr.add_password(None, url, auth_info[0], auth_info[1])
            opener.add_handler(urllib2.HTTPBasicAuthHandler(password_mgr))
        if proxy_info:
            opener.add_handler(urllib2.ProxyHandler({"http" : "http://%(user)s:%(pass)s@%(host)s:%(port)d" % proxy_info}))
        urllib2.install_opener(opener)
        if os.path.isfile(TOKEN_FILENAME):
            self.token = file(TOKEN_FILENAME).read()
        else:
            self.token = 0
        self.progress_handler = default_progress_handler

    def get_content_type(self, filename):
        return mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    def encode_multipart_formdata(self, fields, files):
        """
        fields is a sequence of (name, value) elements for regular form fields.
        files is a sequence of (name, filename, value) elements for data to be uploaded as files
        Return (content_type, body) ready for httplib.HTTP instance
        """
        BOUNDARY = '----------ThIs_Is_tHe_bouNdaRY_$'
        CRLF = '\r\n'
        L = []
        for (key, value) in fields:
                L.append('--' + BOUNDARY)
                L.append('Content-Disposition: form-data; name="%s"' % key)
                L.append('')
                L.append(value)
        for (key, filename) in files:
                L.append('--' + BOUNDARY)
                L.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (key, filename))
                L.append('Content-Type: %s' % self.get_content_type(filename))
                L.append('Content-Transfer-Encoding: binary')
                L.append('')
                fp = file(filename, 'rb')
                L.append(fp.read())
                fp.close()
        L.append('--' + BOUNDARY + '--')
        L.append('')
        body = CRLF.join(L)
        content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
        return content_type, body

    def urlopen(self, action, body=None, headers=None):
        try:
            url = '%s?action=%s&identity=%s' % (self.url, action, self.identity)
            print url
            if self.token:
                url += "&token=%s" % self.token
            # print url
            if body:
                req = urllib2.Request(url, body, headers)
            else:
                req = urllib2.Request(url)
            result = urllib2.urlopen(req).read()
            print '=>', result[:64]
            if len(result) == 1:
                return eval(result)
            else:
                return result
        except urllib2.HTTPError, e:
            if e.code == 404:
                raise Exception(u"Echec - code 404 (page non trouvée)")
            else:
                raise Exception(u"Echec - code %d (%s)" % (e.code, e.msg))
        except urllib2.URLError, e:
            raise Exception("Echec - cause:", e.reason)
        except Exception, e:
            raise

    def has_token(self):
        self.progress_handler.display(u"Vérification du jeton ...")
        return self.token and self.urlopen('has_token')

    def get_token(self):
        self.progress_handler.display(u"Récupération du jeton ...")
        if force_token:
            self.token = self.urlopen('force_token')
        else:
            self.token = self.urlopen('get_token')
        if not self.token:
            return 0
        else:
            file(TOKEN_FILENAME, 'w').write(self.token)
            return 1

    def rel_token(self):
        if not self.token:
            return 1
        self.progress_handler.display(u"Libération du jeton ...")
        if not self.urlopen('rel_token'):
            return 0
        else:
            self.token = 0
            if os.path.exists(TOKEN_FILENAME):
                os.remove(TOKEN_FILENAME)
            return 1

    def do_download(self):
        self.progress_handler.display(u"Téléchargement de la base ...")
        data = self.urlopen('download')
        if data:
            f = file(sqlinterface.DB_FILENAME, 'wb')
            f.write(data)
            f.close()
            self.progress_handler.display(u'%d octets transférés.' % len(data))
        else:
            self.progress_handler.display(u'Pas de base présente sur le serveur.')
            if os.path.isfile(sqlinterface.DB_FILENAME):
                self.progress_handler.display("Utilisation de la base locale ...")
        return 1

    def download(self):       
        if self.has_token():
            self.progress_handler.display(u"Jeton déjà pris => pas de download")
            return 1
        elif self.get_token():
            self.progress_handler.set(30)
            if self.do_download():
                self.progress_handler.set(90)
                return 1
            else:
                self.progress_handler.set(90)
                self.rel_token()
                self.progress_handler.display(u"Le download a échoué")
                return 0
        else:
            self.progress_handler.display("Impossible de prendre le jeton.")
            return 0
       
    def do_upload(self):
        self.progress_handler.display("Envoi vers le serveur ...")
        content_type, body = self.encode_multipart_formdata([], [("database", "./gertrude.db")])
        headers = {"Content-Type": content_type, 'Content-Length': str(len(body))}
        return self.urlopen('upload', body, headers)

    def upload(self):
        if not self.has_token():
            self.progress_handler.display(u"Pas de jeton présent => pas d'envoi vers le serveur.")
            return 0
        return self.do_upload()

    def Load(self, progress_handler=default_progress_handler):
        self.progress_handler = progress_handler
        if self.download():
            result = FileConnection().Load(progress_handler)
        elif self.do_download():
            result = FileConnection().Load(progress_handler)[0], 1
        else:
            result = None, 0
        return result

    def Save(self, progress_handler=default_progress_handler):
        self.progress_handler = progress_handler
        return FileConnection().Save() and self.upload()

    def Restore(self, progress_handler=default_progress_handler):
        self.progress_handler = progress_handler
        return FileConnection().Restore()
    
    def Exit(self, progress_handler=default_progress_handler):
        self.progress_handler = progress_handler
        return FileConnection().Save() and self.rel_token()

class FileConnection(object):
    def __init__(self):
        self.backup = None

    def Backup(self, progress_handler=default_progress_handler):
        progress_handler.display('Sauvegarde ...')
        try:
            if os.path.isfile(sqlinterface.DB_FILENAME):
                if not os.path.isdir(BACKUPS_DIRECTORY):
                    os.mkdir(BACKUPS_DIRECTORY)
                self.backup = 'backup_%d.db' % time.time()
                shutil.copyfile(sqlinterface.DB_FILENAME, BACKUPS_DIRECTORY + '/' + self.backup)
        except Exception, e:
            progress_handler.display('Impossible de faire la sauvegarde' + e)
                    
    def Load(self, progress_handler=default_progress_handler):
        self.Backup(progress_handler)
        if not os.path.isfile(sqlinterface.DB_FILENAME):
            try:
                sql_connection.create(progress_handler)
            except:
                sql_connection.close()
                os.remove(sqlinterface.DB_FILENAME)
                raise
        creche = sql_connection.load(progress_handler)
        return creche, 0

    def Save(self, progress_handler=default_progress_handler):
        sql_connection.commit()
        return True
    
    def Restore(self, progress_handler=default_progress_handler):
        sql_connection.commit()
        sql_connection.close()
        backup = self.backup
        self.Backup(progress_handler)
        if backup:
            shutil.copyfile(BACKUPS_DIRECTORY + '/' + backup, sqlinterface.DB_FILENAME)
        return True

    def Exit(self, progress_handler=default_progress_handler):
        sql_connection.commit()
        sql_connection.close()
        return True        

