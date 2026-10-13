"""Canonical vertex and edge IDs shared by all generated maps."""
import math
from app.board import ROWS
R=70.0
CX=450.0
Y0=170.0
VERTEX_POINTS=[]
EDGE_PAIRS=[]
vertex_index={}
edge_index={}
HEX_VERTICES=[]
for row,count in enumerate(ROWS):
    for col in range(count):
        cx=CX+(col-(count-1)/2)*math.sqrt(3)*R
        cy=Y0+row*1.5*R
        ids=[]
        for k in range(6):
            a=math.radians(-90+60*k)
            p=(round(cx+R*math.cos(a),3),round(cy+R*math.sin(a),3))
            if p not in vertex_index:
                vertex_index[p]=len(VERTEX_POINTS)
                VERTEX_POINTS.append(p)
            ids.append(vertex_index[p])
        HEX_VERTICES.append(ids)
        for k in range(6):
            pair=tuple(sorted((ids[k],ids[(k+1)%6])))
            if pair not in edge_index:
                edge_index[pair]=len(EDGE_PAIRS)
                EDGE_PAIRS.append(pair)
VERTICES={f'v{i}' for i in range(len(VERTEX_POINTS))}
EDGES={f'e{i}' for i in range(len(EDGE_PAIRS))}
