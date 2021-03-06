#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import
import re
import os
import json


import gransk.core.helper as helper
import gransk.core.abstract_subscriber as abstract_subscriber
import six


class Subscriber(abstract_subscriber.Subscriber):
  """Class for extracting metadata from documents using Apache Tika."""
  CONSUMES = [helper.EXTRACT_META]

  def setup(self, config):
    """
    Load mediatype mapping from file. This is used to determine document type.

    :param config: Configuration object.
    :type config: ``dict``
    """
    self.config = config
    typecache = {}
    media_path = os.path.join(
        config[helper.CODE_ROOT], 'utils', 'media_types.txt')

    with open(media_path) as inp:
      current = None
      for line in inp:
        if len(line.strip()) == 0 or line.startswith('#'):
          continue

        if line.strip().startswith('-'):
          apptype = line.strip().partition('-')[2]
          apptype = apptype.strip()
          typecache[current].append(re.escape(apptype))
        else:
          current = line.strip()
          typecache[current] = []

    pattern_list = []

    for _type, patterns in typecache.items():
      pattern_list.append(u'(?P<%s>(%s))' % (_type, u'|'.join(patterns)))

    self.typepattern = re.compile(u'|'.join(pattern_list), re.I)

  def __extract_metadata(self, doc, payload):
    filename = os.path.basename(doc.path).encode('utf-8')
    files = {
        'Accept': 'application/json',
        'Content-Disposition': 'attachment; filename=%s' % filename
    }

    payload.seek(0)
    connection = self.config[helper.INJECTOR].get_http_connection()
    connection.request('PUT', '/meta', payload.read(), files)
    payload.seek(0)

    response = connection.getresponse()

    result = json.loads(response.read().decode('utf-8'))

    response.close()

    return result

  def consume(self, doc, payload):
    """
    Upload document to Apache Tika and parse results.

    :param doc: Document object.
    :param payload: File pointer beloning to document.
    :type doc: ``gransk.core.document.Document``
    :type payload: ``file``
    """
    meta = {}

    max_size = self.config.get(helper.MAX_FILE_SIZE, 0)

    if max_size > 0 and doc.meta['size'] > max_size:
      return

    try:
      meta = self.__extract_metadata(doc, payload)
      application_type = meta.get(u'Content-Type')
      for match in self.typepattern.finditer(application_type):
        doc.set_type(match.lastgroup)
    except Exception as err:
      doc.meta['meta_error'] = six.text_type(err)

    for key, value in meta.items():
      doc.meta[key.replace('.', '_').replace(':', '_')] = value
