#!/usr/bin/env python
import sys, time, threading, xmlrpclib, unittest, cPickle, shelve, socket, random# xmlrpclib is the client side module
from datetime import datetime, timedelta
from xmlrpclib import Binary, ServerProxy
from getopt import getopt
from SimpleXMLRPCServer import SimpleXMLRPCServer

BSIZE = 8
NUM_REPLICA = 2

# Presents a HT interface
class SimpleHT:
  def __init__(self):
    self.server_no = int(sys.argv[1])
    self.server_list = sys.argv[2:]
    self.num_servers = len(sys.argv[2:])
    # number of replicas more than total number of servers.
    if(NUM_REPLICA > self.num_servers - 1):
      sys.exit(4)
    self.data = shelve.open('dataStore_' + str(self.server_no))
    self.rep = [None] * NUM_REPLICA  
    i = 0
    while i < NUM_REPLICA:
      self.rep[i] = shelve.open('dataStore_' + str(self.server_no) + str(i))
      i += 1
    self.recovery()

  def recovery(self):
    if len(self.data) == 0:
      try:
        data_server = ServerProxy("http://localhost:" + self.server_list[self.server_no + 1])
        # ---------Ver. 1------------
        # can't pickle DB objects   
        # data = pickle.loads(data_server.getAllButLast().data) 
        # ---------Ver. 2------------      
        # with open('dataStore_' + str(self.server_no), 'w') as handle:
        #   handle.write(data_server.getReplica(str(0)).data)
        data = cPickle.loads(data_server.getReplica(Binary(str(0))).data)
        for (x, y) in data:
          self.data[x] = y
        self.data.close()
        self.data = shelve.open('dataStore_' + str(self.server_no))
        i = 0
        while i < NUM_REPLICA:         
          if i == NUM_REPLICA - 1:
            replica_server = ServerProxy("http://localhost:" + self.server_list[(self.server_no - 1) % self.num_servers])
            rep_data = cPickle.loads(replica_server.getReplica(Binary(str(i - 1))).data)
            for (x, y) in rep_data:
              self.rep[i][x] = y
          else:
            rep_data = cPickle.loads(data_server.getReplica(Binary(str(i + 1))).data)
            for (x, y) in rep_data:
              self.rep[i][x] = y
          self.rep[i].close()
          self.rep[i] = shelve.open('dataStore_' + str(self.server_no) + str(i))
          i += 1
      except socket.error: 
        print('Both neighbours are not connected, recovery failed.')
    else:
      pass

  def reset(self):
    self.data.clear()
    self.data.close()
    self.data = shelve.open('dataStore_' + str(self.server_no))
    i = 0
    while i < NUM_REPLICA:
      self.rep[i].clear()
      self.rep[i].close()
      self.rep[i] = shelve.open('dataStore_' + str(self.server_no) + str(i))
      i += 1
    return True

  def getReplica(self, i):
    return Binary(cPickle.dumps(self.rep[int(i.data)].items()))

  def get(self, key):
    key = key.data
    if key.startswith('replica_'):
      rep_no = int(key[8])
      rv = self.rep[rep_no][key[9:]]
    else:
      rv = self.data[key]
    print(cPickle.loads(rv))
    return Binary(rv)

  def put(self, key, value):
    key = key.data
    # I don't think it neccessary to unmarshal the data when storing and marshal again when reading since the data is not accessed or modified on the server side.
    # value = pickle.loads(value.data)
    value = value.data
    if key.startswith('replica_'):
      rep_no = int(key[8])
      self.rep[rep_no][key[9:]] = value
      self.rep[rep_no].close()
      self.rep[rep_no] = shelve.open('dataStore_' + str(self.server_no) + str(rep_no))
    else:
      self.data[key] = value
      self.data.close()
      self.data = shelve.open('dataStore_' + str(self.server_no))
    return True

  def delete(self, key):
    key = key.data
    if key.startswith('replica_'):
      rep_no = int(key[8])
      del self.rep[rep_no][key[9:]]
      self.rep[rep_no].close()
      self.rep[rep_no] = shelve.open('dataStore_' + str(self.server_no) + str(rep_no))
    else:
      del self.data[key]
      self.data.close()
      self.data = shelve.open('dataStore_' + str(self.server_no))
    return True

  def corrupt(self, path, size):
    path = path.data
    hash_val =  sum(ord(i) for i in path)
    blk_list = []
    for i in range(int(size.data)):
      if (hash_val + i) % self.num_servers == self.server_no:
        blk_list.append(i)
    print blk_list
    target = random.choice(blk_list)
    key = str(target) + path
    try:
      data_org = self.data[str(target) + path]
      print('+++++Orig data: ',cPickle.loads(data_org))
      data_err = cPickle.dumps((data_org[0], 333))
      self.data[key] = data_err
      print('+++++NEW data: ', self.data[key])
      self.data.close()
      self.data = shelve.open('dataStore_' + str(self.server_no))
      print('Block number %d of file path "%s" on this server is corrupted.' % (target, path))
      return True
    except keyError:
      return False
       
  def __del__(self):
    self.data.close()
    i = 0
    while i < NUM_REPLICA:
      self.rep[i].close()
      i += 1

def main():
  index = int(sys.argv[1])
  server_list = sys.argv[2:]
  port = server_list[index]
  serve(port)

# Start the xmlrpc server
def serve(port):
  # Create a new server instance.
  file_server = SimpleXMLRPCServer(('localhost', int(port)))
  # Registers the XML-RPC introspection functions system.listMethods, system.methodHelp and system.methodSignature.
  file_server.register_introspection_functions()
  # Create a SimpleHT instance
  sht = SimpleHT()
  # Register a function that can respond to XML-RPC requests. If name is given, 
  # it will be the method name associated with function, otherwise function.__name__ will be used.
  file_server.register_function(sht.getReplica)
  file_server.register_function(sht.reset)
  file_server.register_function(sht.get)
  file_server.register_function(sht.put)
  file_server.register_function(sht.delete)
  file_server.register_function(sht.corrupt)
  file_server.register_function(sht.recovery)  
  # Run the server's main loop
  file_server.serve_forever()

"""#####################Testing Purpose#########################"""

# Execute the xmlrpc in a thread ... needed for testing
class serve_thread:
  def __call__(self, port):
    serve(port)

# Wrapper functions so the tests don't need to be concerned about Binary blobs
class Helper:
  def __init__(self, caller):
    self.caller = caller

  def put(self, key, val, ttl):
    return self.caller.put(Binary(key), Binary(val), ttl)

  def get(self, key):
    return self.caller.get(Binary(key))

  def write_file(self, filename):
    return self.caller.write_file(Binary(filename))

  def read_file(self, filename):
    return self.caller.read_file(Binary(filename))

# SimpleHTTest inherit from TestCase, it's a TestSuite that defines several TestCases.
class SimpleHTTest(unittest.TestCase): 
  def test_direct(self):
    helper = Helper(SimpleHT())
    self.assertEqual(helper.get("test"), {}, "DHT isn't empty")
    self.assertTrue(helper.put("test", "test", 10000), "Failed to put")
    self.assertEqual(helper.get("test")["value"], "test", "Failed to perform single get")
    self.assertTrue(helper.put("test", "test0", 10000), "Failed to put")
    self.assertEqual(helper.get("test")["value"], "test0", "Failed to perform overwrite")
    self.assertTrue(helper.put("test", "test1", 2), "Failed to put" )
    self.assertEqual(helper.get("test")["value"], "test1", "Failed to perform overwrite")
    time.sleep(2)
    self.assertEqual(helper.get("test"), {}, "Failed expire")
    self.assertTrue(helper.put("test", "test2", 20000))
    self.assertEqual(helper.get("test")["value"], "test2", "Store new value")

    helper.write_file("test")
    helper = Helper(SimpleHT())

    self.assertEqual(helper.get("test"), {}, "DHT isn't empty")
    helper.read_file("test")
    self.assertEqual(helper.get("test")["value"], "test2", "Load unsuccessful!")
    self.assertTrue(helper.put("some_other_key", "some_value", 10000))
    self.assertEqual(helper.get("some_other_key")["value"], "some_value", "Different keys")
    self.assertEqual(helper.get("test")["value"], "test2", "Verify contents")

  # Test via RPC
  def test_xmlrpc(self):
    output_thread = threading.Thread(target=serve_thread(), args=(51234, ))
    output_thread.setDaemon(True)
    output_thread.start()

    time.sleep(1)
    helper = Helper(xmlrpclib.Server("http://127.0.0.1:51234"))
    self.assertEqual(helper.get("test"), {}, "DHT isn't empty")
    self.assertTrue(helper.put("test", "test", 10000), "Failed to put")
    self.assertEqual(helper.get("test")["value"], "test", "Failed to perform single get")
    self.assertTrue(helper.put("test", "test0", 10000), "Failed to put")
    self.assertEqual(helper.get("test")["value"], "test0", "Failed to perform overwrite")
    self.assertTrue(helper.put("test", "test1", 2), "Failed to put" )
    self.assertEqual(helper.get("test")["value"], "test1", "Failed to perform overwrite")
    time.sleep(2)
    self.assertEqual(helper.get("test"), {}, "Failed expire")
    self.assertTrue(helper.put("test", "test2", 20000))
    self.assertEqual(helper.get("test")["value"], "test2", "Store new value")

if __name__ == "__main__":
  main()