"""
Viz routines for args.
"""
import collections
import itertools
import string

import tskit
import networkx as nx
import numpy as np
import pydot

def draw(
    ts,
    ax,
    *,
    use_ranked_times=None,
    tweak_x=None,
    arrows=False,
    pos=None,
    node_size=None,
    font_size=None,
    node_color=None,
    reverse_x_axis=None,
    ):
    """
    Draw a graphical representation of a tree sequence. If a metadata key
    called "name" exists for the node, it is taken as
    a node label, otherwise the node ID will be used as a label instead.

    If use_ranked times is True, the y axis uses the time ranks, with the
    same times sharing a rank. If False, it uses the true (tree sequence)
    times. If None, times from the tree sequence are not used and the
    standard dot layout is used.
    
    tweak_x is a dict of {u: x_adjustment_percent} which allows
    the x position of node u to be hand-adjusted by adding or
    subtracting a percentage of the total x width of the plot
    
    If pos is passed in, it should be a dictionary mapping nodes to
    positions.
    
    node_size, font_size, and node_color are all passed to nx.draw directly.
    In particular this means that node_color can either be a single
    colour for all nodes (e.g. `mpl.colors.to_hex(mpl.pyplot.cm.tab20(1))`)
    or a dict of node_id -> colours.
    
    if reverse_x_axis is True, the graph is reflected horizontally 
    """
    if node_size is None:
        node_size = 200
    if font_size is None:
        font_size = 9
    G = convert_nx(ts)
    labels = {}
    for nd in ts.nodes():
        try:
            labels[nd.id] = str(nd.metadata["name"])
        except (TypeError, KeyError):
            labels[nd.id] = str(nd.id)

    if pos is None:
        pos = nx_get_dot_pos(G, reverse_x_axis)

    if use_ranked_times is not None:
        if use_ranked_times:
            _, inv = np.unique(ts.tables.nodes.time, return_inverse=True)
            ranked_times = (np.cumsum(np.bincount(inv)) - 1)[inv]
            for i, p in pos.items():
                p[1] = ranked_times[i]
        else:
            times = ts.tables.nodes.time
            for i, p in pos.items():
                p[1] = times[i]
    if tweak_x:
        plot_width = np.ptp([x for x, _ in pos.values()])
        for node, tweak_val in tweak_x.items():
            pos[node] = pos[node] + np.array([(tweak_val/100*plot_width), 0])
    # Draw just the nodes
    nx.draw(
        G,
        pos,
        node_color=node_color,
        node_shape="o",
        node_size=node_size,
        font_size=font_size,
        labels=labels,
        ax=ax,
        edgelist=[],
    )
    # Now add the edges
    nx.draw_networkx_edges(
        G,
        pos,
        edgelist=G.edges(),
        arrowstyle="-|>" if arrows else "-",
        ax=ax,
    )

    return pos

def label_nodes(ts, labels=None):
    """
    Adds a metadata item called "name" to each node, whose value
    is given by the labels dictionary passed in. If labels is None (default),
    use the dictionary {0: 'A', 1: 'B', 2: 'C', ... 26: 'Z'}.
    Any nodes without a corresponding key in the labels dictionary will
    simply have their metadata value set to their node id.
    
    Note that this means that if no labels are given, nodes 26 onwards
    will be labelled with numbers rather than ascii uppercase letters.
    """
    if labels is None:
        labels = {i: lab for i, lab in enumerate(string.ascii_uppercase)}
    tables = ts.dump_tables()

    tables.nodes.clear()
    for i, nd in enumerate(ts.tables.nodes):
        m = nd.metadata or {}
        # assume we can set metadata to a dict: e.g. that node.metadata_schema is json
        tables.nodes.append(nd.replace(metadata={**m, "name": labels.get(i, i)}))
    return tables.tree_sequence()


def convert_nx(ts):
    """
    Returns the specified tree sequence as an networkx directed graph.
    """
    G = nx.DiGraph()
    edges = collections.defaultdict(list)
    for edge in ts.edges():
        edges[(edge.child, edge.parent)].append((edge.left, edge.right))
    for node in ts.nodes():
        G.add_node(node.id, time=node.time, flags=node.flags)
    for edge, intervals in edges.items():
        G.add_edge(*edge, intervals=intervals)
    return G


def nx_get_dot_pos(G, reverse_x_axis=None):
    """
    Layout using graphviz's "dot" algorithm and return a dict of positions in the
    format required by networkx. We assume that the nodes have a "time" attribute
    """
    if reverse_x_axis is None:
        reverse_x_axis = False
    P=nx.drawing.nx_pydot.to_pydot(G) # switch to a Pydot representation
    nodes_at_time = collections.defaultdict(list)
    for nd in P.get_nodes():
        nodes_at_time[float(nd.get("time"))].append(nd)
    
    # First cluster all nodes at the same times (probably mostly samples)
    for t, nodes in nodes_at_time.items():
        if len(nodes) > 1:
            S=pydot.Cluster(f"cluster_t{t}")
            for nd in nodes:
                S.add_node(nd)
            P.add_subgraph(S)
    graphviz_bytes = P.create_dot()
    graphs = pydot.graph_from_dot_data(graphviz_bytes.decode())
    assert len(graphs) == 1
    graph = graphs[0]
    # negate at least the y axis coords, to get the graph going in the direction we want
    if reverse_x_axis:
        coord_direction = np.array([-1, -1])
    else:
        coord_direction = np.array([1, -1])
        
    return {
        # [1:-1] snips off enclosing quotes
        int(n.get_name()): np.fromstring(n.get_pos()[1:-1], sep=",") * coord_direction
        # need to iterate over this graph and also all the subgraphs to get all the nodes
        for g in itertools.chain([graph], graph.get_subgraphs()) for n in g.get_nodes()
        if n.get_pos() and n.get_name().isdigit()
    }

