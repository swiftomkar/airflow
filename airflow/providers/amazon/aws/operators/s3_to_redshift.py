#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from typing import List, Optional, Union

from airflow.exceptions import AirflowException
from airflow.models import BaseOperator
from airflow.providers.amazon.aws.hooks.aws_dynamodb import AwsDynamoDBHook
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.utils.decorators import apply_defaults


class S3ToRedshiftTransfer(BaseOperator):
    """
    Executes an COPY command to load files from s3 to Redshift

    :param schema: reference to a specific schema in redshift database
    :type schema: str
    :param table: reference to a specific table in redshift database
    :type table: str
    :param s3_bucket: reference to a specific S3 bucket
    :type s3_bucket: str
    :param s3_key: reference to a specific S3 key
    :type s3_key: str
    :param redshift_conn_id: reference to a specific redshift database
    :type redshift_conn_id: str
    :param aws_conn_id: reference to a specific S3 connection
    :type aws_conn_id: str
    :param verify: Whether or not to verify SSL certificates for S3 connection.
        By default SSL certificates are verified.
        You can provide the following values:

        - ``False``: do not validate SSL certificates. SSL will still be used
                 (unless use_ssl is False), but SSL certificates will not be
                 verified.
        - ``path/to/cert/bundle.pem``: A filename of the CA cert bundle to uses.
                 You can specify this argument if you want to use a different
                 CA cert bundle than the one used by botocore.
    :type verify: bool or str
    :param copy_options: reference to a list of COPY options
    :type copy_options: list
    """

    template_fields = ()
    template_ext = ()
    ui_color = '#ededed'

    @apply_defaults
    def __init__(  # pylint: disable=too-many-arguments
            self,
            schema: str,
            table: str,
            data_source: Optional[str] = 's3',
            s3bucket_or_dynamodbtable: Optional[str] = None,
            s3_key: Optional[str] = None,
            redshift_conn_id: str = 'redshift_default',
            aws_conn_id: str = 'aws_default',
            verify: Optional[Union[bool, str]] = None,
            copy_options: Optional[List] = None,
            operation='UPSERT',
            autocommit: bool = False,
            *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.schema = schema
        self.table = table
        self.data_source = data_source
        self.s3bucket_or_dynamodbtable = s3bucket_or_dynamodbtable
        self.s3_key = s3_key
        self.copy_options = copy_options or []
        self.autocommit = autocommit
        self.operation = operation
        self._postgres_hook = PostgresHook(redshift_conn_id)
        if data_source == 's3':
            self._data_source_hook = S3Hook(aws_conn_id=aws_conn_id, verify=verify).get_credentials()
        else:
            self._data_source_hook = AwsDynamoDBHook(aws_conn_id=aws_conn_id, verify=verify).get_credentials()

    def _copy_data(self, credentials, schema=None, table=None):
        copy_query = """
                    COPY {schema}.{table}
                    FROM '{data_source}://{s3bucket_or_dynamodbtable}/{s3_key}'
                    with credentials
                    'aws_access_key_id={access_key};aws_secret_access_key={secret_key}'
                    {copy_options};
                """.format(schema=schema,
                           table=table,
                           data_source=self.data_source,
                           s3bucket_or_dynamodbtable=self.s3bucket_or_dynamodbtable,
                           s3_key=self.s3_key,
                           access_key=credentials.access_key,
                           secret_key=credentials.secret_key,
                           copy_options=self.copy_options)

        self.log.info('Executing COPY command...')
        self._postgres_hook.run(copy_query, self.autocommit)
        self.log.info("COPY command complete...")

    def execute(self, context):
        if self.operation == "COPY":
            self._copy_data(self._data_source_hook, self.schema, self.table)
        else:
            raise AirflowException("Invalid operation; options [COPY, UPSERT]")
