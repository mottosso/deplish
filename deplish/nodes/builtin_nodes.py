import node


class DagNodeDot(node.DagNode):
    """Cosmetic. Simply collect connections

    A dot node is a node that simply collects connections
    and passes them on. It's mostly for the benefit of the
    user interface.

    """

    def __init__(self, name=""):
        super(DagNodeDot, self).__init__(name)

    def _defineInputs(self):
        return []
        
    def _defineOutputs(self):
        return [] 

    def _defineAttributes(self):
        return []

    def executeList(self):
        pass


# class DagNodeCoalesce(node.DagNode):
#     """
#     The coalesce node takes a variety of inputs and collates them into a single
#     sequence.  This is done by creating symlinks in a temporary location on disk.
#     """
#     # TODO
#     def __init__(self, name=""):
#         super(DagNodeCoalesce, self).__init__(name)

#     def _defineInputs(self):
#         return []
        
#     def _defineOutputs(self):
#         return [] 

#     def _defineAttributes(self):
#         return []

#     def executeList(self):
#         pass