import depends_node
import depends_data_packet


class DagNodeTest(depends_node.DagNode):
    """Implementation of the Windows `dir` command"""

    def _defineInputs(self):
        return []

    def _defineOutputs(self):
        return []

    def _defineAttributes(self):
        docPath = ("A path to do a windows 'cmd' command on.")
        return [depends_node.DagNodeAttribute('listWindowsPath',
                "", docString=docPath)]

    def execute(self):
        print "executing awesome node!"
