#!/usr/bin/env python
from xmlrpclib import Binary, ServerProxy
import cPickle

class corruptionSim():
	def corruptSingleFile(self):
		path = '/1.txt'
		num_serv = 4
		meta_server = ServerProxy("http://localhost:" + '2222')
		meta = cPickle.loads(meta_server.get(Binary(path)).data)
		size = (meta['st_size'] - 1) // 8 + 1
		server0 = ServerProxy("http://localhost:3333")
		server0.corrupt(Binary(path), Binary(str(size)))
		server2 = ServerProxy("http://localhost:5555")
		server2.corrupt(Binary(path), Binary(str(size)))

if __name__ == '__main__':
	corruption = corruptionSim()
	corruption.corruptSingleFile()