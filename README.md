# Distributed_Fault-Tolerant_Multilevel-Filesystem
The *python FUSE library is used to implement this custom filesystem

This is a client-server based filesystem that uses one metadata server and multiple data servers to balance the workload given that the bandwidth for each server is limited. The data is stored distributedly on multiple data servers with fault-tolerance and redundancy mechanisms.

Design assumptions and requirements are:

• There are multiple dataservers and a single metaserver. Metaserver is assumed to be very reliable and robust which never fails.

• The data blocks of the file are stored in the round-robin fashion as mentioned above but, there are two redundant copies of the same block are stored in the following two dataservers.
  o Replica 1: [x%N, (x+1)%N, (x+2)%N, (x+3)%N …] where x is hash(path)
  o Replica 2: [(x+1)%N, (x+2)%N, (x+3)%N, (x+4)%N, …]
  o Replica 3: [(x+2)%N, (x+3)%N, (x+4)%N, (x+5)%N, …]
  o By storing 3 replicas of each block means that replication factor is 3.
  
• The data-servers store the data blocks in persistent storage (hard disk) to allow for recovery upon a crash. The file used to store the data will be referred to as ‘data store’.
  o You can still use an additional in-memory data structure, but you should always write to disk before returning an RPC call. This means that the primary database for the server is on disk. It is suggested that you use Python shelve for a dictionary object backed by a persistent file.
  
• Your dataservers should tolerate server crashes – where server process is terminated and restarted at later point in time.
  o In case server process crashes and restarts (e.g., server rebooted), the server should be able to recover and resume serving data using the data stored on its local disk.
  o In case persistent storage of the server is completely lost (e.g., server disk is failed and replaced with new disk), then it should be able to recover using the replica(s) rom its adjacent servers and copy the data blocks that are to be stored on the current server.
  
• Dealing with data corruption – Corruption in data store.
  o Use checksum of data blocks in the data-servers to verify the data.
  o When there is read call from the user, the FUSE client should read from one of the replicas (randomly chosen) and verify the checksum. If the checksum does not match, the client should read from another replica and write back to the corrupt server if the client detects data corruption.
  o Provide an XMLRPC call with name ‘corrupt’ which takes the path of a file as an argument. The function should simulate the corruption of at least one of the bytes of any of the data blocks (or its checksum) of that file stored on that server.

Dealing with writes while a server is unavailable
  o All writes must commit to all replicas and receive acknowledgements from the servers before the FUSE client proceeds further.
  o When server is down, any write calls on the FUSE folder should back. The FUSE client should keep retrying the operation until it succeds and the write call should not return till then.
  o Reads should return successfully even if a single replica is available and the checksum verifies correctly.
• You should test your system with number of data-servers N>=4 and three replicas.

Program arguments and guidelines:

The program should take the arguments in the following format:
python metaserver.py <port for metaserver>
python dataserver.py <0 indexed server number> <ports for all dataservers separated by spaces>
python distributedFS.py <fusemount directory> <metaserver port> <dataservers ports separated by spaces>
example (N=4):
  
python metaserver.py 2222
python dataserver.py 0 3333 4444 5555 6666
python dataserver.py 1 3333 4444 5555 6666
python dataserver.py 2 3333 4444 5555 6666
python dataserver.py 3 3333 4444 5555 6666
python distributedFS.py fusemount 2222 3333 4444 5555 6666

The local ports are bold and adjacent server’s ports are italicized for understanding.

*python2
