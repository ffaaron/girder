#!/usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
#  Copyright 2014 Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import base64
import boto
import hashlib
import hmac
import os
import time
import uuid

from .abstract_assetstore_adapter import AbstractAssetstoreAdapter
from girder.models.model_base import ValidationException
from girder import logger


class S3AssetstoreAdapter(AbstractAssetstoreAdapter):
    """
    This assetstore type stores files on S3. It is responsible for generating
    HMAC-signed messages that authorize the client to communicate directly with
    the S3 server where the files are stored.
    """

    CHUNK_LEN = 1024 * 1024 * 64
    HMAC_TTL = 120  # Num. of seconds message is valid

    @staticmethod
    def validateInfo(doc):
        """
        Makes sure the root field is a valid absolute path and is writeable.
        """
        if 'prefix' not in doc:
            doc['prefix'] = ''
        while len(doc['prefix']) and doc['prefix'][0] == '/':
            doc['prefix'] = doc['prefix'][1:]
        while len(doc['prefix']) and doc['prefix'][-1] == '/':
            doc['prefix'] = doc['prefix'][:-1]
        if not doc.get('bucket'):
            raise ValidationException('Bucket must not be empty.', 'bucket')
        if not doc.get('secret'):
            raise ValidationException(
                'Secret key must not be empty.', 'secretKey')
        if not doc.get('accessKeyId'):
            raise ValidationException(
                'Access key ID must not be empty.', 'accessKeyId')

        # Make sure we can write into the given bucket using boto
        try:
            conn = boto.connect_s3(aws_access_key_id=doc['accessKeyId'],
                                   aws_secret_access_key=doc['secret'])
            bucket = conn.lookup(bucket_name=doc['bucket'], validate=False)
            testKey = boto.s3.key.Key(
                bucket=bucket, name=os.path.join(doc['prefix'], 'test'))
            testKey.set_contents_from_string('')
        except:
            logger.exception('S3 assetstore validation exception')
            raise ValidationException('Unable to write into bucket "{}".'
                                      .format(doc['bucket']), 'bucket')

        return doc

    def __init__(self, assetstore):
        """
        :param assetstore: The assetstore to act on.
        """
        self.assetstore = assetstore

    def initUpload(self, upload):
        """
        Build the request required to initiate an authorized upload to S3.
        """
        uid = uuid.uuid4()
        key = '/'.join((uid[0:2], uid[2:4], uid))
        path = '/{}/{}'.format(self.assetstore['bucket'], key)
        headers = '\n'.join(('x-amz-acl: private',))
        url = 'https://{}.s3.amazonaws.com/{}'.format(
            self.assetstore['bucket'], key)

        chunked = upload['size'] > self.CHUNK_LEN
        expires = int(time.time() + self.HMAC_TTL)

        upload['behavior'] = 's3'
        upload['s3'] = {
            'chunked': chunked,
            'chunkLength': self.CHUNK_LEN
        }

        if chunked:
            msg = ('POST', '', '', expires, headers, path + '?uploads')
            url += '?uploads'
            signature = base64.b64encode(hmac.new(
                self.assetstore['secret'],
                '\n'.join(msg), hashlib.sha1).digest())

            upload['s3']['request'] = {
                'method': 'POST',
                'url': url,
                'headers': {
                    'Authorization': 'AWS {}:{}'.format(
                        self.assetstore['accessKeyId'], signature),
                    'Date': expires,
                    'x-amz-acl': 'private'
                }
            }
        else:
            msg = ('PUT', '', upload['mimeType'], expires, headers, path)
            signature = base64.b64encode(hmac.new(
                self.assetstore['secret'],
                '\n'.join(msg), hashlib.sha1).digest())

            upload['s3']['request'] = {
                'method': 'PUT',
                'url': url,
                'headers': {
                    'Authorization': 'AWS {}:{}'.format(
                        self.assetstore['accessKeyId'], signature),
                    'Date': expires,
                    'x-amz-acl': 'private'
                }
            }

        return upload

    def uploadChunk(self, upload, chunk):
        pass  # TODO

    def requestOffset(self, upload):
        raise Exception('S3 assetstore does not support requestOffset.')

    def finalizeUpload(self, upload, file):
        pass  # TODO

    def downloadFile(self, file, offset=0, headers=True):
        pass  # TODO

    def deleteFile(self, file):
        pass  # TODO
