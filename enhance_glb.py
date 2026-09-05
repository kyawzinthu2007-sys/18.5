import struct, json, math, os
import numpy as np

src='/mnt/data/tso_work/frontend/tso-ai-robot.glb'
out='/mnt/data/tso_work/frontend/tso-ai-robot.glb'
b=open(src,'rb').read()
assert b[:4]==b'glTF'
total=struct.unpack_from('<I',b,8)[0]
pos=12
json_bytes=None; bin_bytes=None
while pos<total:
    clen,ctype=struct.unpack_from('<II',b,pos); pos+=8
    chunk=b[pos:pos+clen]; pos+=clen
    if ctype==0x4E4F534A: json_bytes=chunk
    elif ctype==0x4E4942: bin_bytes=chunk
j=json.loads(json_bytes.rstrip(b' \t\r\n\x00'))
if 'buffers' not in j: raise RuntimeError('No buffers')
# Only one BIN buffer in this model.
raw=bytearray(bin_bytes)

# Helper to read accessor data.
def accessor_array(ai):
    a=j['accessors'][ai]
    bv=j['bufferViews'][a['bufferView']]
    comp=a['componentType']
    types={5121:np.uint8,5123:np.uint16,5125:np.uint32,5126:np.float32}
    dtype=types[comp]
    ncomp={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT2':4,'MAT3':9,'MAT4':16}[a['type']]
    stride=bv.get('byteStride', np.dtype(dtype).itemsize*ncomp)
    start=bv.get('byteOffset',0)+a.get('byteOffset',0)
    count=a['count']
    if stride==np.dtype(dtype).itemsize*ncomp:
        arr=np.frombuffer(raw, dtype=dtype, count=count*ncomp, offset=start).reshape((count,ncomp))
    else:
        arr=np.empty((count,ncomp),dtype=dtype)
        for i in range(count):
            arr[i]=np.frombuffer(raw,dtype=dtype,count=ncomp,offset=start+i*stride)
    return arr.copy()

# Append a normal bufferView/accessor per primitive. This preserves all existing
# animation channels and mesh topology while enabling smooth, premium shading.
def align4(x): return (x+3)&~3

new_normals=0
for mi,mesh in enumerate(j.get('meshes',[])):
    for prim in mesh.get('primitives',[]):
        attrs=prim.get('attributes',{})
        if 'POSITION' not in attrs: continue
        pos_arr=accessor_array(attrs['POSITION']).astype(np.float64)
        if pos_arr.shape[1] != 3: continue
        idx = accessor_array(prim['indices']).reshape(-1).astype(np.int64) if 'indices' in prim else np.arange(len(pos_arr),dtype=np.int64)
        normals=np.zeros_like(pos_arr)
        # Area-weighted vertex normals.
        tri=idx.reshape(-1,3)
        p0=pos_arr[tri[:,0]]; p1=pos_arr[tri[:,1]]; p2=pos_arr[tri[:,2]]
        fn=np.cross(p1-p0,p2-p0)
        np.add.at(normals,tri[:,0],fn)
        np.add.at(normals,tri[:,1],fn)
        np.add.at(normals,tri[:,2],fn)
        lens=np.linalg.norm(normals,axis=1)
        lens[lens<1e-12]=1
        normals=(normals/lens[:,None]).astype(np.float32)
        # Append to BIN, 4-byte aligned.
        start=align4(len(raw))
        if start>len(raw): raw.extend(b'\x00'*(start-len(raw)))
        blob=normals.tobytes(order='C')
        raw.extend(blob)
        bv_idx=len(j['bufferViews'])
        j['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(blob),'target':34962})
        acc_idx=len(j['accessors'])
        j['accessors'].append({'bufferView':bv_idx,'componentType':5126,'count':len(normals),'type':'VEC3','min':[-1,-1,-1],'max':[1,1,1]})
        attrs['NORMAL']=acc_idx
        new_normals += 1

# Refine the PBR response for a softer, more premium toy-like finish.
for m in j.get('materials',[]):
    p=m.setdefault('pbrMetallicRoughness',{})
    name=(m.get('name') or '').lower()
    if 'soft white' in name:
        p['roughnessFactor']=0.32
    elif 'warm white' in name:
        p['roughnessFactor']=0.30
    elif 'face glass' in name:
        p['roughnessFactor']=0.08
        p['metallicFactor']=0.45
    elif 'eye glow' in name:
        p['roughnessFactor']=0.12
        p['metallicFactor']=0.08
    elif 'tso purple' in name or 'light purple' in name:
        p['roughnessFactor']=0.24

# Add useful extras documenting the upgrade.
j.setdefault('asset',{})['generator']='Talentshowoff TSO AI character — smooth high-detail shading upgrade'
j['asset']['extras']={'smoothNormalsAdded':True,'originalAnimationsPreserved':True}

# Update buffer length.
j['buffers'][0]['byteLength']=len(raw)
# Compact JSON then 4-byte pad.
jbytes=json.dumps(j,separators=(',',':'),ensure_ascii=False).encode('utf-8')
jbytes += b' ' * ((4-len(jbytes)%4)%4)
# BIN is already 4-byte aligned.
binout=bytes(raw)
# Rebuild GLB.
total_len=12+8+len(jbytes)+8+len(binout)
outb=bytearray()
outb += b'glTF' + struct.pack('<II',2,total_len)
outb += struct.pack('<II',len(jbytes),0x4E4F534A) + jbytes
outb += struct.pack('<II',len(binout),0x4E4942) + binout
open(out,'wb').write(outb)
print('wrote',out,'bytes',len(outb),'normals',new_normals)
