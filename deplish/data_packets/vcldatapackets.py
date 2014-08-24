#
# Depends
# Copyright (C) 2014 by Andrew Gardner & Jonas Unger.  All rights reserved.
# BSD license (LICENSE.txt for details).
#

import data_packet


"""
"""


###############################################################################
###############################################################################
class DataPacketImage(data_packet.DataPacket):
	"""
	Everything needed to load a simple image.  
	Image filename(s).  
	"""
	def __init__(self, sourceNode, sourceOutputName):
		data_packet.DataPacket.__init__(self, sourceNode, sourceOutputName)
		self.filenames['filename'] = ""


###############################################################################
###############################################################################
class DataPacketLightprobe(DataPacketImage):
	"""
	Everything needed to load a lightprobe(s).  
	Image and transform filenames.  
	"""
	def __init__(self, sourceNode, sourceOutputName):
		DataPacketImage.__init__(self, sourceNode, sourceOutputName)
		self.filenames['transform'] = ""


###############################################################################
###############################################################################
class DataPacketPointcloud(data_packet.DataPacket):
	"""
	Everything needed to load a pointcloud(s).  
	Cloud and their transforms filenames.
	"""
	def __init__(self, sourceNode, sourceOutputName):
		data_packet.DataPacket.__init__(self, sourceNode, sourceOutputName)
		self.filenames['filename'] = ""
		self.filenames['transform'] = ""


###############################################################################
###############################################################################
class DataPacketLightfield(data_packet.DataPacket):
	"""
	Everything needed to load a lightfield(s).
	A filename, a bounding box filename, and a transform filename.
	(This presumes the parameters are baked into the lightfield itself - resolution, etc)
	"""
	def __init__(self, sourceNode, sourceOutputName):
		data_packet.DataPacket.__init__(self, sourceNode, sourceOutputName)
		self.filenames['filename'] = ""
		self.filenames['boundingBox'] = ""
		self.filenames['transform'] = ""


###############################################################################
###############################################################################
class DataPacketBoundingBox(data_packet.DataPacket):
	"""
	Everything needed to load a bounding box.  
	A bounding box and transform filename.
	"""
	def __init__(self, sourceNode, sourceOutputName):
		data_packet.DataPacket.__init__(self, sourceNode, sourceOutputName)
		self.filenames['filename'] = ""
		self.filenames['transform'] = ""


###############################################################################
###############################################################################
class DataPacketColorspace(data_packet.DataPacket):
	"""
	Everything needed to load a colorspace transform(s).
	A filename.
	"""
	def __init__(self, sourceNode, sourceOutputName):
		data_packet.DataPacket.__init__(self, sourceNode, sourceOutputName)
		self.filenames['filename'] = ""
		
