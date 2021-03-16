#! /usr/bin/env python3

from enum import Enum
import re
import subprocess
import sys

class DrmPropertyType(Enum):
  Range = 0
  Enum = 1
  Blob = 2
  Unknown = 3

  @staticmethod
  def fromstring(str):
    if str == 'range':
      return DrmPropertyType.Range
    elif str == 'enum':
      return DrmPropertyType.Enum
    elif str == 'blob':
      return DrmPropertyType.Blob
    else:
      raise ValueError('Unknown property type {}'.format(str))

class DrmProperty(object):
  def __init__(self, id, name):
    self.id = id
    self.name = name
    self.type = DrmPropertyType.Unknown
    self.immutable = False

    self.range = {'min':-1, 'max':-1, 'val':-1}
    self.enum = {'entries':[], 'val':-1}
    self.blob = ''

  def __str__(self):
    ret = 'id={} name={} type={} immutable={}'.format(self.id, self.name, self.type, self.immutable)
    if self.type == DrmPropertyType.Range:
      ret += '\n'
      ret += '   ' + str(self.range)
    elif self.type == DrmPropertyType.Enum:
      ret += '\n'
      ret += '   ' + str(self.enum)
    elif self.type == DrmPropertyType.Blob:
      ret += '\n'
      ret += '   val={}'.format(self.blob)
    return ret

  def valstr(self):
    if self.type == DrmPropertyType.Range:
      return str(self.range['val'])
    elif self.type == DrmPropertyType.Enum:
      for e in self.enum['entries']:
        if e['val'] == self.enum['val']:
          return str(e['name'])
      return 'VALNOTFOUND'
    elif self.type == DrmPropertyType.Blob:
      return self.blob

  def parserange(self, lines):
    m = re.match('\t\tvalues: ([0-9]*) ([0-9]*)', lines[0])
    if not m:
      raise ValueError('range re error, {}'.format(lines[0]))
    self.range['min'] = int(m[1])
    self.range['max'] = int(m[2])

    m = re.match('\t\tvalue: ([0-9]*)', lines[1])
    if not m:
      raise ValueError('rangeval re error, {}'.format(lines[1]))
    self.range['val'] = int(m[1])

    return 2

  def parseenum(self, lines):
    pfx = '\t\tenums: '
    if not lines[0].startswith(pfx):
      raise ValueError('Unknown enum str, {}'.format(lines[0]))

    vals = lines[0][len(pfx):]
    m = re.findall('([^=]+)=([0-9]+)', vals)
    if not m:
      raise ValueError('enum re error, {}'.format(lines[0]))

    for e in m:
      self.enum['entries'].append({'name': e[0], 'val': int(e[1])})

    m = re.match('\t\tvalue: ([0-9]*)', lines[1])
    if not m:
      raise ValueError('enumval re error, {}'.format(lines[1]))
    self.enum['val'] = int(m[1])

    return 2

  def parseblob(self, lines):
    offset = 0
    pfx = '\t\tblobs'
    if not lines[0].startswith(pfx):
      raise ValueError('Unknown blobs str, {}'.format(lines[0]))
    offset += 1

    for l in lines[offset:]:
      if l:
        break
      offset += 1

    pfx = '\t\tvalue'
    if not lines[offset].startswith(pfx):
      raise ValueError('Unknown blob val str, {}'.format(lines[offset]))
    offset += 1

    blobval_re = re.compile('\t\t\t([0-9a-fA-F]+)')
    for l in lines[offset:]:
      m = blobval_re.match(l)
      if not m or not m.group(1):
        break
      self.blob += m.group(1)
      offset += 1

    return offset

  def parse(self, lines):
    offset = 0
    while offset < len(lines):
      l = lines[offset]
      m = re.match('\t\tflags: (immutable )?(range|enum|blob)', l)
      if not m:
        raise ValueError('propflags re error, {}'.format(l))
      self.type = DrmPropertyType.fromstring(m[2])
      if m[1]:
        self.immutable = True
      offset += 1

      if self.type == DrmPropertyType.Range:
        offset += self.parserange(lines[offset:])
      elif self.type == DrmPropertyType.Enum:
        offset += self.parseenum(lines[offset:])
      elif self.type == DrmPropertyType.Blob:
        offset += self.parseblob(lines[offset:])
      break
    return offset


class DrmObjectType(Enum):
  CRTC = 1
  Connector = 2

  @staticmethod
  def fromstring(str):
    if str == 'CRTC':
      return DrmObjectType.CRTC
    elif str == 'Connector':
      return DrmObjectType.Connector
    else:
      raise ValueError('Unknown object type {}'.format(str))

class DrmObject(object):
  def __init__(self, type_name, id, name):
    self.type = DrmObjectType.fromstring(type_name)
    self.id = int(id)
    self.name = name
    self.properties = []

  def __str__(self):
    return 'id={} name={} type={}'.format(self.id, self.name, self.type)

  def parse(self, lines):
    offset = 0
    while offset < len(lines):
      l = lines[offset]
      if not l.startswith('\t'):
        break

      m = re.match('\t([0-9]*) (.*):', l)
      if not m:
        raise ValueError('Propname re error, {}'.format(l))

      prop = DrmProperty(m[1], m[2])

      offset += 1
      offset += prop.parse(lines[offset:])
      self.properties.append(prop)
    return offset

  def getprop(self, propname):
    for p in self.properties:
      if p.name == propname:
        return p
    return None

kCrtcs = []
kConnectors = []

def proptest(conn=None, prop=None, val=None):
  if conn and prop:
    subprocess.check_output(['proptest', str(conn.id), 'connector', str(prop.id), str(val)])
    return

  kCrtcs.clear()
  kConnectors.clear()

  ret = subprocess.check_output(['proptest'])

  lines = ret.decode('ascii', errors='ignore').splitlines()
  offset = 0
  while offset < len(lines):
    if lines[offset].startswith('\t'):
      raise ValueError('Parsing error!')

    m = re.match(r'(Connector|CRTC) ([0-9]*)( \()?(\S*-[0-9]*)?(\))?', lines[offset])
    offset += 1
    if not m:
      continue

    obj = DrmObject(m[1], m[2], m[4])
    if obj.type == DrmObjectType.CRTC:
      kCrtcs.append(obj)
    else:
      kConnectors.append(obj)

    offset += obj.parse(lines[offset:])

def printvals(conn=None):
  for c in kConnectors:
    if conn != None and c.id != conn:
      continue

    # Only show connected connectors (determined by having an EDID present)
    p = c.getprop('EDID')
    if not p or not p.valstr():
      continue

    print(c)
    p = c.getprop('HDCP Content Type')
    if p:
      print('  Content Type: {}'.format(p.valstr()))
    else:
      print('  Unsupported')
    p = c.getprop('Content Protection')
    if p:
      print('  Content Protection: {}'.format(p.valstr()))
    else:
      print('  Unsupported')

def main():
  proptest()
  if len(sys.argv) == 1:
    printvals()
  elif len(sys.argv) == 2:
    printvals(conn=int(sys.argv[1]))
  elif len(sys.argv) == 3:
    printvals(conn=int(sys.argv[1]))
    for c in kConnectors:
      if c.id != int(sys.argv[1]):
        continue
      p = c.getprop('Content Protection')
      proptest(conn=c, prop=p, val=int(sys.argv[2]))
      break
    proptest()
    printvals(conn=int(sys.argv[1]))
  elif len(sys.argv) == 4:
    printvals(conn=int(sys.argv[1]))
    for c in kConnectors:
      if c.id != int(sys.argv[1]):
        continue
      p = c.getprop('HDCP Content Type')
      proptest(conn=c, prop=p, val=int(sys.argv[3]))
      p = c.getprop('Content Protection')
      proptest(conn=c, prop=p, val=int(sys.argv[2]))
      break
    proptest()
    printvals(conn=int(sys.argv[1]))

if __name__ == '__main__':
  main()
