#!/usr/bin/env python 
from __future__ import print_function, absolute_import, division
import logging, cPickle, math, random, socket
from collections import defaultdict # dict subclass that calls a factory function to supply missing values
from errno import ENOENT, ENOTEMPTY  # error, no entry; dir not empty
# The pyxattr module is not integrated in Linux
# from xattr import ENOATTR #the attribute name is invalid
from stat import S_IFDIR, S_IFLNK, S_IFREG # directory, symbolic link, regular file
from sys import argv, exit
from time import time, sleep

from xmlrpclib import Binary, ServerProxy

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn

BSIZE = 8
NUM_REPLICA = 2

class getError(Exception):
    pass
    """Failure during get_data"""

class Memory(LoggingMixIn, Operations):
    def __init__(self, meta_port, data_ports):
        self.meta_server = ServerProxy("http://localhost:" + meta_port)
        self.data_servers = [ServerProxy("http://localhost:" + i) for i in data_ports]
        self.meta_server.reset()
        for data_server in self.data_servers:
            data_server.reset()
        self.fd = 0
        now = time()
        self.put_meta('/', dict(st_mode=(S_IFDIR | 0o755), st_ctime=now, st_mtime=now, st_atime=now, st_nlink=2, files=[]))

    def hash(self, path):
        return sum(ord(i) for i in path)

    def get_meta(self, path):
        return cPickle.loads(self.meta_server.get(Binary(path)).data)

    def put_meta(self, path, meta):
        return self.meta_server.put(Binary(path), Binary(cPickle.dumps(meta)))

    def del_meta(self, path):
        return self.meta_server.delete(Binary(path))

    def get_data(self, path, drange):
        def careful_get_data(): 
            rep_no = 0          
            try:
                rep_no = random.choice(list_rep)
                print('-----------------rep_no: ', rep_no, 'BLK number: ', i)
                byte = ''
                checksum = 0
                if rep_no == 0:
                    try:
                        byte, checksum = cPickle.loads(self.data_servers[server_no].get(Binary(str(i) + path)).data)
                        new_checksum = self.checksum(byte)
                        if new_checksum == checksum:
                            result.append(byte)
                            return (byte, checksum)
                        else:
                            corrupt_list.append(list_rep.pop(0))
                            return careful_get_data()
                    except socket.error:
                        list_rep.remove(0)
                        return careful_get_data()
                else:
                    try:
                        byte, checksum = cPickle.loads(self.data_servers[(server_no + rep_no) % len(self.data_servers)].get(Binary('replica_' + str(rep_no - 1) + str(i) + path)).data)
                        new_checksum = self.checksum(byte)
                        if new_checksum == checksum:
                            result.append(byte)
                            return (byte, checksum)
                        else:
                            currupt_list.append(list_rep.pop(list_rep.index(rep_no)))
                            return careful_get_data()
                    except socket.error:
                        list_rep.remove(rep_no)
                        return careful_get_data()
            except IndexError:
                print('IndexError: All replicas offline or corrupted.')
                raise getError('There is at least one block in this file that all of its replicas are either offline or corrupted!')   
             
        hash_val = self.hash(path)
        result = []  
        for i in drange:
            # determine server that stores the first block            
            server_no = (hash_val + i) % len(self.data_servers)
            list_rep = range(NUM_REPLICA + 1)
            # list of servers whose data is corrupted
            corrupt_list = [] 
            value = careful_get_data()
            # Recover the corrupted data.
            print('blk_no::::::::::::::::::', i, corrupt_list)
            if corrupt_list:
                for k in corrupt_list:
                    if k == 0:   
                        while True:
                            try: 
                                self.data_servers[server_no].put(Binary(str(i) + path), Binary(cPickle.dumps(value)))
                                break
                            except socket.error:
                                print("socketError: [Errno 111] Connection to server %d refused", k)
                                sleep(3)
                                continue                            
                    else: 
                        while True:
                            try: 
                                self.data_servers[(server_no + k) % len(self.data_servers)].put(Binary('replica_' + str(k - 1) + str(i) + path), Binary(cPickle.dumps(value)))
                                break
                            except socket.error:
                                print("socketError: [Errno 111] Connection to server %d refused", k)
                                sleep(3)
                                continue
                    print('Corruption in server %d detected and cocrrected! File Path: %s, Block Number: %d \n.' % (k, path, i))
        return result


    def put_data(self, path, data, drange):
        hash_val = self.hash(path)
        start = drange[0]
        for i in drange:
            value = (data[i - start], self.checksum(data[i - start]))
            server_no = (hash_val + i) % len(self.data_servers)
            while True:
                try:
                    self.data_servers[server_no].put(Binary(str(i) + path), Binary(cPickle.dumps(value)))
                    break
                except socket.error:
                    print("socketError: [Errno 111] Connection refused")
                    sleep(3)
                    continue             
            j = 1
            while j <= NUM_REPLICA:
                # to set number of maximum retries: for i in range(max):
                while True:
                    try:
                        self.data_servers[(server_no + j) % len(self.data_servers)].put(Binary('replica_' + str(j - 1) + str(i) + path), Binary(cPickle.dumps(value)))                    
                        break
                    except socket.error:
                        print("socketError: [Errno 111] Connection refused")
                        sleep(3)
                        continue                     
                j += 1
  
    def del_data(self, path, drange):
        hash_val = self.hash(path)
        for i in drange:
            server_no = (hash_val + i) % len(self.data_servers)
            self.data_servers[server_no].delete(Binary(str(i) + path))  
            j = 1
            while j <= NUM_REPLICA:         
                self.data_servers[(server_no + j) % len(self.data_servers)].delete(Binary('replica_' + str(j - 1) + str(i) + path))
                j += 1

    def seperatepath(self, path):
        child = path[path.rfind('/')+1:]
        parent = path[:path.rfind('/')]
        if parent == '':
            parent = '/'
        return parent, child

    def checksum(self, byte):
        checksum = 0
        for bit in byte:
            checksum ^= ord(bit)
        return checksum

    ############################################### Data Manipulation on Memory #######################################################
    def chmod(self, path, mode):
        meta = self.get_meta(path)
        meta['st_mode'] &= 0o770000
        meta['st_mode'] |= mode
        self.put_meta(path, meta)
        return 0

    def chown(self, path, uid, gid):
        meta = self.get_meta(path)
        meta['st_uid'] = uid # user id of the owner
        meta['st_gid'] = gid # group id of the owner
        self.put_meta(path, meta)
    
    def create(self, path, mode):
        meta = dict(st_mode=(S_IFREG | mode), st_nlink=1, st_size=0, st_ctime=time(), st_mtime=time(), st_atime=time())
        self.put_meta(path, meta)
        parent, child = self.seperatepath(path)
        pmeta = self.get_meta(parent)
        pmeta['files'].append(child)
        self.put_meta(parent, pmeta)     
        self.fd += 1
        return self.fd

    def getattr(self, path, fh=None):
        meta = self.get_meta(path)
        # Empty dictionaries evaluate to False in Python
    	if not meta:
            raise FuseOSError(ENOENT)
        return meta
    # getxattr() retrieves the value of the extended attribute identified by name 
    # and associated with the given path in the file system. The length of the attribute value is returned.
    def getxattr(self, path, name, position=0):
        meta = self.get_meta(path)
        attrs = meta.get('attrs', {})
        try:
            return attrs[name]
        except KeyError:
            return ''       # Should raise ENOATTR error

    def listxattr(self, path):
        meta = self.get_meta(path)
        attrs = meta.get('attrs', {})
        return attrs.keys()

    # Usage: mkdir -m '666' dirName to make directory with permission
    def mkdir(self, path, mode):
    	meta = dict(st_mode=(S_IFDIR | mode), st_nlink=2, st_size=0, st_ctime=time(), st_mtime=time(), st_atime=time(), files=[])
    	self.put_meta(path, meta)
        parent, child = self.seperatepath(path)
        pmeta = self.get_meta(parent)
        pmeta['files'].append(child)
        pmeta['st_nlink'] += 1
        self.put_meta(parent, pmeta)

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def read(self, path, size, offset, fh):
        meta = self.get_meta(path)
        print('++++++++++++++++++++++++++++++++++ FILE SIZE: +++============================: ', meta['st_size'])
    	if offset + size > meta['st_size']:
    		size = meta['st_size'] - offset # limit the read within the file.
        drange = range(offset // BSIZE, (offset + size -1) // BSIZE + 1)
        try:
            dd = ''.join(self.get_data(path, drange))
            dd = dd[offset % BSIZE : offset % BSIZE + size] # take the needed part from the string
            return dd
        except getError as e:
            print('getError: ', e.message)

    def readdir(self, path, fh):
    	meta = self.get_meta(path)
        return ['.', '..'] + meta['files']

    def readlink(self, path):
        meta = self.get_meta(path)
        return ''.join(self.get_data(path,range((meta['st_size'] - 1) // BSIZE + 1)))

    def removexattr(self, path, name):
        meta = self.gat_meta(path)
        attrs = meta.get('attrs', {})
        try:
            del attrs[name]
        except KeyError:
            pass    # Should raise ENOATTR error
        self.put_meta(path, p)

    #This could be very inefficient especially moving big casaded folders
    def rename(self, old, new):
        def recursive_move(old, new, file_name):
            file_path = old + '/' + file_name
            meta = self.get_meta(file_path)
            new_path = new + '/' + file_name
            if meta['st_mode'] & 0o770000 == S_IFDIR:
                for sub_file_name in meta['files']:
                    recursive_move(file_path, new_path, sub_file_name)
            else:
                drange = range((meta['st_size'] - 1) // BSIZE + 1)
                file_data = self.get_data(file_path, drange)
                self.del_data(file_path, drange)
                self.put_data(new_path, file_data, drange)
            self.del_meta(file_path)
            self.put_meta(new_path, meta)

        oldparent, oldchild = self.seperatepath(old)
        oldpmeta = self.get_meta(oldparent)
        oldmeta = self.get_meta(old)
        newparent,newchild = self.seperatepath(new)
        newpmeta = self.get_meta(newparent)


        if oldmeta['st_mode'] & 0o770000 == S_IFDIR:
            oldpmeta['st_nlink'] -= 1
            if oldparent == newparent:
                newpmeta['st_nlink'] -= 1
            newpmeta['st_nlink'] += 1
            for file_name in oldmeta['files']:
                recursive_move(old, new, file_name)
        else:
            drange = range((oldmeta['st_size'] - 1) // BSIZE + 1)
            file_data = self.get_data(old, drange)
            self.del_data(old, drange)
            self.put_data(new, file_data, drange)

        oldpmeta['files'].remove(oldchild)
        if oldparent == newparent:
            newpmeta['files'].remove(oldchild)
        newpmeta['files'].append(newchild)
        if oldparent != newparent:
            self.put_meta(oldparent, oldpmeta)
        self.del_meta(old)      
        self.put_meta(newparent, newpmeta)
        self.put_meta(new, oldmeta)
      
    def rmdir(self, path):
    	# if dir not empty need to raise an error!
        if len(self.get_meta(path)['files']) > 0:
    		raise FuseOSError(ENOTEMPTY);
        self.del_meta(path)
        parent, child = self.seperatepath(path)
        pmeta = self.get_meta(parent)
        pmeta['files'].remove(child)
        pmeta['st_nlink'] -= 1
        self.put_meta(parent, pmeta)

    def setxattr(self, path, name, value, options, position=0):
        attrs = self.get_meta(path).setdefault('attrs', {})
        attrs[name] = value

    def statfs(self, path):
        return dict(f_BSIZE=512, f_blocks=4096, f_bavail=2048)

    def symlink(self, target, link):
        print('target:', target)
        meta = dict(st_mode=(S_IFLNK | 0o777), st_nlink=1, st_size=len(target))
        self.put_meta(link, meta)
        parent, child = self.seperatepath(link)
        pmeta = self.get_meta(parent)
        print('pmeta: ', pmeta)
        pmeta['files'].append(child)
        self.put_meta(parent, pmeta)

        data = [target[i : i + BSIZE] for i in range(0, len(target), BSIZE)]
        drange = range(len(data))
        self.put_data(link, data, drange) 

    def truncate(self, path, length, fh=None):
        meta = self.get_meta(path)
        size = meta['st_size']
        if length == size:
            return 0
        else:
            data = []            
            blk_off = size % BSIZE         
            len_off = length % BSIZE   
            if length > size:
                blk_no = size // BSIZE 
                len_no = (length - 1) // BSIZE + 1
                drange = range(blk_no, len_no)
                if blk_off == 0:  
                    data = [''.ljust(BSIZE, '\x00') if i * BSIZE + 8 <= length else ''.ljust(len_off, '\x00') for i in drange]    
                else:
                    data = self.get_data(path, range(blk_no, blk_no + 1))
                    if len_no == blk_no + 1:
                        data[0] = data[0].ljust(len_off, '\x00') if len_off != 0 else data[0].ljust(BSIZE, '\x00')
                    else:
                        data[0] = data[0].ljust(BSIZE, '\x00')
                        data_latter = [''.ljust(BSIZE, '\x00') if i * BSIZE + 8 <= length else ''.ljust(len_off, '\x00') for i in drange[1:]]
                        data = data + data_latter
                        
                self.put_data(path, data, drange)
            else:
                blk_no = (size - 1) // BSIZE + 1
                len_no = length // BSIZE
                if len_off == 0:
                    self.del_data(path, range(len_no, blk_no))
                else:
                    data = self.get_data(path, range(len_no, len_no + 1))
                    data[0] = data[0][:len_off]
                    self.put_data(path, data, range(len_no, len_no + 1))
                    self.del_data(path, range(len_no + 1, blk_no))                  
        meta['st_size'] = length
        self.put_meta(path, meta)

    def unlink(self, path):       
        parent, child = self.seperatepath(path)
        pmeta = self.get_meta(parent)
        pmeta['files'].remove(child)
        self.put_meta(parent, pmeta)
        meta = self.get_meta(path)
        self.del_data(path, range((meta['st_size'] - 1) // BSIZE + 1))
        self.del_meta(path)

    def utimens(self, path, times=None):
        now = time()
        atime, mtime = times if times else (now, now)
        meta = self.get_meta(path)
        meta['st_atime'] = atime
        meta['st_mtime'] = mtime
        self.put_meta(path, meta)

    '''
    Behavior of lseek():The lseek() function allows the file offset to be set beyond the end of the file 
    (but this does not change the size of the file). If data is later written at this point, subsequent reads
     of the data in the gap (a "hole") return null bytes ('\0') until data is actually written into the gap.
    '''
    def write(self, path, data, offset, fh):
    	data_size = len(data)
        if data_size == 0: return 0
        meta = self.get_meta(path)
        size = meta['st_size']
        size_blk = size // BSIZE

        drange = range(offset // BSIZE, (offset + data_size -1) // BSIZE + 1)
        blk_no = offset // BSIZE
        blk_off = offset % BSIZE
        # cut data to blocks: [:BSIZE - offset%BSIZE] and rest...
        data_seg = [data[:BSIZE - blk_off]] + [data[i : i + BSIZE] for i in range(BSIZE - blk_off, data_size, BSIZE)]
        # write offset after end of file.
        if offset > size:
            drange = range(size_blk, (offset + data_size -1) // BSIZE + 1)
            # if offset in last block, keep the content of last block and resize it to offset % BSIZE, else fill null bytes in the middle.
            if size % BSIZE != 0:
                left = self.get_data(path, range(size_blk, size_blk + 1))
                if blk_off == 0:
                    left[-1].ljust(BSIZE, '\x00')
                    for i in range(blk_no - size_blk - 1):
                        left.append(''.ljust(BSIZE, '\x00'))
                else: 
                    if size % BSIZE + data_size <= BSIZE:
                        left[-1].ljust(size % BSIZE + data_size, '\x00')
                    else:
                        left[-1].ljust(BSIZE, '\x00')
                        for i in range(blk_no - size_blk - 1):
                            left.append(''.ljust(BSIZE, '\x00'))
                        left.append(''.ljust(blk_off, '\x00'))
            else:
                left = [''.ljust(BSIZE, '\x00') for i in range(blk_no - size_blk)]
                # Inline if-else EXPRESSION must always contain else clause
                if blk_off != 0: left.append(''.ljust(blk_off, '\x00'))
            if blk_off != 0: mod_data = left[:-1] + [left[-1] + data_seg[0]] + data_seg[1:]
            else: mod_data = left + data_seg
        else:            
            if blk_off != 0: 
                left = self.get_data(path, range(blk_no, blk_no + 1))
                mod_data = [left[-1] + data_seg[0]] + data_seg[1:]
            else: mod_data = data_seg
            if offset + data_size // BSIZE != 0 and offset + data_size < size:
                right = self.get_data(path, range(blk_no, blk_no + 1))
                mod_data = mod_data[:-1] + [mod_data[-1]] + right[(offset + data_size) % BSIZE:]
        self.put_data(path, mod_data, drange) 
        size = offset + data_size if offset + data_size > size else size      
        meta['st_size']= size
        self.put_meta(path, meta)       
        return size

if __name__ == '__main__':
    if len(argv) < 4:
        print('usage: %s <mountpoint> <meta_server_port> <data_server_port>' % argv[0]) # print program usage
        exit(1)
    logging.basicConfig(level=logging.DEBUG)
    fuse = FUSE(Memory(argv[2], argv[3:]), argv[1], foreground=True, debug=True)