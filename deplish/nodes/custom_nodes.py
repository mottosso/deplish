import node


class DagNodeTest(node.DagNode):
    """Implementation of the Windows `dir` command"""

    def _defineInputs(self):
        return []

    def _defineOutputs(self):
        return []

    def _defineAttributes(self):
        docPath = ("A path to do a windows 'cmd' command on.")
        return [node.DagNodeAttribute('listWindowsPath',
                "", docString=docPath)]

    def execute(self):
        print "executing awesome node!"
