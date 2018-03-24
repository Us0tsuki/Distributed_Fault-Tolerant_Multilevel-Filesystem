#!/usr/bin/env python
import sys, pickle, time, threading, xmlrpclib, unittest # xmlrpclib is the client side module
from datetime import datetime, timedelta
from xmlrpclib import Binary
from getopt import getopt
from SimpleXMLRPCServer import SimpleXMLRPCServer

# Presents a HT interface
class SimpleHT:
  def __init__(self):
    self.data = {}

  def reset(self):
    self.data.clear() 
    return True

  def get(self, key):
    rv = Binary(self.data[key.data]) if key.data in self.data else Binary(pickle.dumps({}))
    return rv

  def put(self, key, value):
    self.data[key.data] = value.data
    return True

  def delete(self, key):
    if key.data in self.data:
      del self.data[key.data]
      return True
    else:
      return False

def main():
  port = sys.argv[1]
  # # extract info. from argv
  # optlist, args = getopt(sys.argv[1:], "", ["port=", "test"])
  # # Convert the list of tuples into a dictionary
  # ol={}
  # for k,v in optlist:
  #   ol[k] = v

  # port = 51234
  # if "--port" in ol:
  #   port = int(ol["--port"])
  # # if '--test' argument exist, perform test and return without serving
  # if "--test" in ol:
  #   sys.argv.remove("--test")
  #   unittest.main()
  #   return
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
  file_server.register_function(sht.reset)
  file_server.register_function(sht.get)
  file_server.register_function(sht.put)
  file_server.register_function(sht.delete)
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