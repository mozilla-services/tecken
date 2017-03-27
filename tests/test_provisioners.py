# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# from datetime import datetime
#
# import constance
# import pytest
# from botocore.stub import ANY, Stubber
# from django.conf import settings
# from freezegun import freeze_time
#
# from atmo.provisioners import Provisioner
#
#
# def test_spark_emr_configuration(mocker):
#     provisioner = Provisioner()
#     mocker.stopall()
#     mock_get = mocker.patch.object(provisioner.session, 'get')
#     provisioner.spark_emr_configuration()
#     mock_get.assert_called_with(provisioner.spark_emr_configuration_url)
#
#
# @freeze_time('2016-04-05 13:25:47')
# @pytest.mark.django_db
# @pytest.mark.parametrize("size,use_spot_instances,groups_length", [
#     [1, True, 1],
#     [10, False, 2],
#     [10, True, 2],
# ])
# def test_job_flow_params(mocker, cluster_provisioner, settings,
#                          size, use_spot_instances, groups_length):
#     config = settings.AWS_CONFIG
#     user_email = 'foo@bar.com'
#     identifier = 'test-flow'
#     emr_release = '1.0'
#     config['LOG_BUCKET'] = 'log-bucket'
#     constance.config.AWS_USE_SPOT_INSTANCES = use_spot_instances
#     params = cluster_provisioner.job_flow_params(
#         user_email=user_email,
#         identifier=identifier,
#         emr_release=emr_release,
#         size=size,
#     )
#
#     assert params['ReleaseLabel'] == 'emr-1.0'
#     assert params['LogUri'] == 's3://log-bucket/clusters/test-flow/2016-04-05T13:25:47+00:00'
#     assert params['Instances']['Ec2KeyName'] == config['EC2_KEY_NAME']
#     assert params['Instances']['KeepJobFlowAliveWhenNoSteps']
#
#     tag_values = [
#         ['Owner', user_email],
#         ['Name', identifier],
#         ['Application', config['INSTANCE_APP_TAG']],
#         ['App', config['ACCOUNTING_APP_TAG']],
#         ['Type', config['ACCOUNTING_TYPE_TAG']],
#     ]
#
#     tags = {}
#     for tag in params['Tags']:
#         tags[tag['Key']] = tag['Value']
#
#     for name, value in tag_values:
#         assert tags[name] == value
#
#     groups = params['Instances']['InstanceGroups']
#     assert len(groups) == groups_length
#     assert groups[0]['InstanceRole'] == 'MASTER'
#     assert groups[0]['InstanceType'] == config['MASTER_INSTANCE_TYPE']
#     assert groups[0]['InstanceCount'] == 1
#
#     if groups_length > 1:
#         assert groups[1]['InstanceRole'] == 'CORE'
#         assert groups[1]['InstanceType'] == config['MASTER_INSTANCE_TYPE']
#         assert groups[1]['InstanceCount'] == size
#         if use_spot_instances:
#             assert groups[1]['Market'] == 'SPOT'
#             assert groups[1]['BidPrice'] == str(settings.CONSTANCE_CONFIG['AWS_SPOT_BID_CORE'][0])
#         else:
#             assert groups[1]['Market'] == 'ON_DEMAND'
#
#
# @freeze_time('2017-02-03 13:48:09')
# def test_cluster_start(mocker, cluster_provisioner, ssh_key):
#     user_email = 'foo@bar.com'
#     identifier = 'test-flow'
#     emr_release = '5.0.0'
#     size = 1
#     public_key = ssh_key.key
#
#     stubber = Stubber(cluster_provisioner.emr)
#     response = {'JobFlowId': '12345'}
#     expected_params = {
#         'Applications': [
#             {'Name': 'Spark'},
#             {'Name': 'Hive'},
#             {'Name': 'Zeppelin'}
#         ],
#         'BootstrapActions': [
#             {
#                 'Name': 'setup-telemetry-cluster',
#                 'ScriptBootstrapAction': {
#                     'Args': [
#                         '--public-key', public_key,
#                         '--email', user_email,
#                         '--efs-dns', constance.config.AWS_EFS_DNS,
#                     ],
#                     'Path': cluster_provisioner.script_uri,
#                 }
#             }
#         ],
#         'Configurations': ANY,
#         'Instances': {
#             'Ec2KeyName': cluster_provisioner.config['EC2_KEY_NAME'],
#             'InstanceGroups': [
#                 {
#                     'InstanceCount': size,
#                     'InstanceRole': 'MASTER',
#                     'InstanceType': cluster_provisioner.config['WORKER_INSTANCE_TYPE'],
#                     'Market': 'ON_DEMAND',
#                     'Name': 'Master',
#                 }
#             ],
#             'KeepJobFlowAliveWhenNoSteps': True,
#         },
#         'JobFlowRole': cluster_provisioner.config['SPARK_INSTANCE_PROFILE'],
#         'LogUri': (
#             's3://log-bucket/%s/%s/2017-02-03T13:48:09+00:00' %
#             (cluster_provisioner.log_dir, identifier)
#         ),
#         'Name': ANY,
#         'ReleaseLabel': 'emr-%s' % emr_release,
#         'ServiceRole': 'EMR_DefaultRole',
#         'Steps': [
#             {
#                 'ActionOnFailure': 'TERMINATE_JOB_FLOW',
#                 'HadoopJarStep': {
#                     'Args': [
#                         cluster_provisioner.zeppelin_uri
#                     ],
#                     'Jar': cluster_provisioner.jar_uri
#                 },
#                 'Name': 'setup-zeppelin'
#             }
#         ],
#         'Tags': [
#             {'Key': 'Owner', 'Value': user_email},
#             {'Key': 'Name', 'Value': identifier},
#             {'Key': 'Application', 'Value': cluster_provisioner.config['INSTANCE_APP_TAG']},
#             {'Key': 'App', 'Value': cluster_provisioner.config['ACCOUNTING_APP_TAG']},
#             {'Key': 'Type', 'Value': cluster_provisioner.config['ACCOUNTING_TYPE_TAG']},
#         ],
#         'VisibleToAllUsers': True,
#     }
#     stubber.add_response('run_job_flow', response, expected_params)
#
#     with stubber:
#         jobflow_id = cluster_provisioner.start(
#             user_email=user_email,
#             identifier=identifier,
#             emr_release=emr_release,
#             size=size,
#             public_key=public_key,
#         )
#         assert jobflow_id == '12345'
#
#
# def test_list_cluster(mocker, cluster_provisioner):
#     today = datetime.today()
#     list_cluster = mocker.patch.object(
#         cluster_provisioner.emr,
#         'list_clusters',
#         return_value={
#             'Clusters': [
#                 {
#                     'Id': 'j-AB1234567890',
#                     'Name': '79d540f0-08d4-4455-a8a6-b3d6ffb9f9f3',
#                     'Status': {
#                         'State': 'WAITING',
#                         'StateChangeReason': {
#                             'Code': 'ALL_STEPS_COMPLETED',
#                             'Message': 'All steps completed.',
#                         },
#                         'Timeline': {
#                             'CreationDateTime': today,
#                         }
#                     },
#                     'NormalizedInstanceHours': 123
#                 },
#             ],
#         }
#     )
#
#     cluster_list = cluster_provisioner.list(today)
#     assert list_cluster.call_count == 1
#     assert cluster_list == [
#         {
#             'jobflow_id': 'j-AB1234567890',
#             'state': 'WAITING',
#             'state_change_reason_code': 'ALL_STEPS_COMPLETED',
#             'state_change_reason_message': 'All steps completed.',
#             'start_time': today,
#         },
#     ]
#
#
# def test_list_cluster_pagination(mocker, cluster_provisioner):
#     today = datetime.today()
#     # first response with pagination marker
#     response = {
#         'Clusters': [
#             {
#                 'Id': 'j-AB1234567890',
#                 'Name': '79d540f0-08d4-4455-a8a6-b3d6ffb9f9f3',
#                 'Status': {
#                     'State': 'WAITING',
#                     'StateChangeReason': {
#                         'Code': 'ALL_STEPS_COMPLETED',
#                         'Message': 'All steps completed.',
#                     },
#                     'Timeline': {
#                         'CreationDateTime': today,
#                     }
#                 },
#                 'NormalizedInstanceHours': 123
#             },
#         ],
#         'Marker': 'some-marker',
#     }
#     # second response without the marker
#     response2 = response.copy()
#     response2.pop('Marker')
#
#     list_cluster = mocker.patch.object(
#         cluster_provisioner.emr,
#         'list_clusters',
#         side_effect=[response, response2],
#     )
#
#     cluster_list = cluster_provisioner.list(today)
#     assert list_cluster.call_count == 2
#
#     cluster = {
#         'jobflow_id': 'j-AB1234567890',
#         'state': 'WAITING',
#         'state_change_reason_code': 'ALL_STEPS_COMPLETED',
#         'state_change_reason_message': 'All steps completed.',
#         'start_time': today,
#     }
#     # cluster list is the same two times, for each pagination page
#     assert cluster_list == [cluster] * 2
#
#
# def test_stop_cluster(cluster_provisioner):
#     stubber = Stubber(cluster_provisioner.emr)
#     response = {}
#     expected_params = {
#         'JobFlowIds': ['12345'],
#     }
#     stubber.add_response('terminate_job_flows', response, expected_params)
#
#     with stubber:
#         cluster_provisioner.stop(jobflow_id='12345')
#
#
# @pytest.mark.django_db
# def test_create_cluster_valid_parameters(cluster_provisioner):
#     """Test that the parameters passed down to run_job_flow are valid"""
#
#     stubber = Stubber(cluster_provisioner.emr)
#     response = {'JobFlowId': 'job-flow-id'}
#     stubber.add_response('run_job_flow', response)
#
#     emr_release = settings.AWS_CONFIG['EMR_RELEASES'][0]
#     with stubber:
#         jobflow_id = cluster_provisioner.start(
#             user_email='user@example.com',
#             identifier='cluster',
#             emr_release=emr_release,
#             size=3,
#             public_key='public-key',
#         )
#
#     assert jobflow_id == response['JobFlowId']
#
#
# def test_cluster_info(cluster_provisioner):
#     cluster_id = 'foo-bar-spam-egs'
#     stubber = Stubber(cluster_provisioner.emr)
#     response = {
#         'Cluster': {
#             'MasterPublicDnsName': '1.2.3.4',
#             'Status': {
#                 'State': 'RUNNING',
#                 'StateChangeReason': {
#                     'Code': 'ALL_STEPS_COMPLETED',
#                     'Message': 'All steps completed.',
#                 },
#                 'Timeline': {
#                     'CreationDateTime': datetime(2015, 1, 1),
#                     'ReadyDateTime': datetime(2015, 1, 1),
#                     'EndDateTime': datetime(2015, 1, 1),
#                 }
#             },
#         },
#     }
#     expected_params = {'ClusterId': cluster_id}
#     stubber.add_response('describe_cluster', response, expected_params)
#
#     with stubber:
#         info = cluster_provisioner.info(cluster_id)
#         assert info == {
#             'start_time': datetime(2015, 1, 1),
#             'state_change_reason_code': 'ALL_STEPS_COMPLETED',
#             'state_change_reason_message': 'All steps completed.',
#             'state': 'RUNNING',
#             'public_dns': '1.2.3.4',
#         }
#
#
# def test_cluster_list(cluster_provisioner):
#     created_after = datetime(1970, 1, 1)
#     created_before = datetime(2020, 1, 1)
#
#     stubber = Stubber(cluster_provisioner.emr)
#     response = {
#         'Clusters': [
#             {
#                 'Id': 'cluster-1',
#                 'Status': {
#                     'State': 'TERMINATED',
#                     'StateChangeReason': {
#                         'Code': 'ALL_STEPS_COMPLETED',
#                         'Message': 'All steps completed.',
#                     },
#                     'Timeline': {
#                         'CreationDateTime': datetime(2015, 1, 1),
#                         'ReadyDateTime': datetime(2015, 1, 1),
#                         'EndDateTime': datetime(2015, 1, 1),
#                     }
#                 },
#             },
#             {
#                 'Id': 'cluster-2',
#                 'Status': {
#                     'State': 'RUNNING',
#                     'StateChangeReason': {
#                         'Code': 'ALL_STEPS_COMPLETED',
#                         'Message': 'All steps completed.',
#                     },
#                     'Timeline': {
#                         'CreationDateTime': datetime(2016, 1, 1),
#                         'ReadyDateTime': datetime(2016, 1, 1),
#                         'EndDateTime': datetime(2016, 1, 1),
#                     }
#                 },
#             },
#         ],
#     }
#     expected_params = {
#         'CreatedAfter': created_after,
#     }
#     expected_result = [
#         {
#             'start_time': datetime(2015, 1, 1),
#             'state': 'TERMINATED',
#             'state_change_reason_code': 'ALL_STEPS_COMPLETED',
#             'state_change_reason_message': 'All steps completed.',
#             'jobflow_id': 'cluster-1',
#         },
#         {
#             'start_time': datetime(2016, 1, 1),
#             'state': 'RUNNING',
#             'state_change_reason_code': 'ALL_STEPS_COMPLETED',
#             'state_change_reason_message': 'All steps completed.',
#             'jobflow_id': 'cluster-2',
#         },
#     ]
#     stubber.add_response('list_clusters', response, expected_params)
#     with stubber:
#
#         info = cluster_provisioner.list(created_after)
#         assert info == expected_result
#
#     # with created_before
#     expected_params = {
#         'CreatedAfter': created_after,
#         'CreatedBefore': created_before,
#     }
#     stubber.add_response('list_clusters', response, expected_params)
#
#     with stubber:
#         info = cluster_provisioner.list(
#             created_after,
#             created_before=created_before,
#         )
#         assert info == expected_result
#
#
# def test_spark_job_add(notebook_maker, spark_job_provisioner):
#     notebook = notebook_maker()
#     identifier = 'test-identifier'
#     key = 'jobs/%s/%s' % (identifier, notebook.name)
#
#     stubber = Stubber(spark_job_provisioner.s3)
#     response = {
#         'Expiration': 'whatever',
#         'ETag': '12345',
#         'VersionId': '1.0',
#     }
#     expected_params = {
#         'Body': notebook,
#         'Bucket': settings.AWS_CONFIG['CODE_BUCKET'],
#         'Key': key,
#     }
#     stubber.add_response('put_object', response, expected_params)
#
#     with stubber:
#         result = spark_job_provisioner.add(
#             identifier=identifier,
#             notebook_file=notebook,
#         )
#         assert result == key
#
#
# def test_spark_job_get(spark_job_provisioner):
#     key = 's3://test/test-notebook.ipynb'
#
#     stubber = Stubber(spark_job_provisioner.s3)
#     response = {
#         'Body': 'content',
#     }
#     expected_params = {
#         'Bucket': settings.AWS_CONFIG['CODE_BUCKET'],
#         'Key': key,
#     }
#     stubber.add_response('get_object', response, expected_params)
#
#     with stubber:
#         result = spark_job_provisioner.get(key)
#         assert result == response
#
#
# def test_spark_job_remove(spark_job_provisioner):
#     key = 's3://test/test-notebook.ipynb'
#
#     stubber = Stubber(spark_job_provisioner.s3)
#     response = {'DeleteMarker': False}
#     expected_params = {
#         'Bucket': settings.AWS_CONFIG['CODE_BUCKET'],
#         'Key': key,
#     }
#     stubber.add_response('delete_object', response, expected_params)
#
#     with stubber:
#         spark_job_provisioner.remove(key)
#
#
# def test_spark_job_results_empty(mocker, spark_job_provisioner):
#     mocker.patch.object(
#         spark_job_provisioner.s3,
#         'list_objects_v2',
#         return_value={},
#     )
#
#     results = spark_job_provisioner.results('job-identifier', True)
#     assert results == {}
#
#
# @pytest.mark.parametrize('public', [True, False])
# def test_spark_job_results(mocker, public, spark_job_provisioner):
#     identifier = 'job-identifier'
#
#     def mocked_list_objects(**kwargs):
#         is_public = kwargs['Bucket'] == settings.AWS_CONFIG['PUBLIC_DATA_BUCKET']
#         pub_prefix = 'pub' if is_public else ''
#         return {
#             'Contents': [
#                 {'Key': '%s/logs/%smy-log.txt' % (identifier, pub_prefix)},
#                 {'Key': '%s/data/%smy-notebook.ipynb' % (identifier, pub_prefix)},
#                 {'Key': '%s/data/%ssub/artifact.txt' % (identifier, pub_prefix)},
#                 # won't be in results because of missing prefixes
#                 {'Key': 'faulty-key.txt'},
#             ]
#         }
#     mocker.patch.object(
#         spark_job_provisioner.s3,
#         'list_objects_v2',
#         mocked_list_objects
#     )
#
#     prefix = 'pub' if public else ''
#
#     results = spark_job_provisioner.results(identifier, public)
#     assert results == {
#         'data': [
#             '%s/data/%smy-notebook.ipynb' % (identifier, prefix),
#             '%s/data/%ssub/artifact.txt' % (identifier, prefix),
#         ],
#         'logs': [
#             '%s/logs/%smy-log.txt' % (identifier, prefix)
#         ]
#     }
#
#
# @freeze_time('2017-02-03 13:48:09')
# @pytest.mark.parametrize('is_public', [True, False])
# def test_spark_job_run(mocker, is_public, spark_job_provisioner):
#     user_email = 'foo@bar.com'
#     identifier = 'test-flow'
#     notebook_key = 'notebook.ipynb'
#     emr_release = '1.0'
#     job_timeout = 60
#     size = 1
#
#     stubber = Stubber(spark_job_provisioner.emr)
#     response = {'JobFlowId': '12345'}
#     expected_params = {
#         'Applications': [
#             {'Name': 'Spark'},
#             {'Name': 'Hive'},
#         ],
#         'BootstrapActions': [
#             {
#                 'Name': 'setup-telemetry-spark-job',
#                 'ScriptBootstrapAction': {
#                     'Args': [
#                         '--timeout', str(job_timeout * 60),
#                     ],
#                     'Path': spark_job_provisioner.script_uri,
#                 }
#             }
#         ],
#         'Configurations': ANY,
#         'Instances': {
#             'Ec2KeyName': spark_job_provisioner.config['EC2_KEY_NAME'],
#             'InstanceGroups': [
#                 {
#                     'InstanceCount': size,
#                     'InstanceRole': 'MASTER',
#                     'InstanceType': spark_job_provisioner.config['WORKER_INSTANCE_TYPE'],
#                     'Market': 'ON_DEMAND',
#                     'Name': 'Master',
#                 }
#             ],
#             'KeepJobFlowAliveWhenNoSteps': False,
#         },
#         'JobFlowRole': spark_job_provisioner.config['SPARK_INSTANCE_PROFILE'],
#         'LogUri': (
#             's3://log-bucket/%s/%s/2017-02-03T13:48:09+00:00' %
#             (spark_job_provisioner.log_dir, identifier)
#         ),
#         'Name': ANY,
#         'ReleaseLabel': 'emr-%s' % emr_release,
#         'ServiceRole': 'EMR_DefaultRole',
#         'Steps': [
#             {
#                 'ActionOnFailure': 'TERMINATE_JOB_FLOW',
#                 'HadoopJarStep': {
#                     'Args': [
#                         spark_job_provisioner.batch_uri,
#                         '--job-name',
#                         identifier,
#                         '--notebook',
#                         's3://telemetry-analysis-code-2/%s' % notebook_key,
#                         '--data-bucket',
#                         settings.AWS_CONFIG['PUBLIC_DATA_BUCKET']
#                         if is_public
#                         else spark_job_provisioner.config['PRIVATE_DATA_BUCKET'],
#                     ],
#                     'Jar': spark_job_provisioner.jar_uri,
#                 },
#                 'Name': 'RunNotebookStep',
#             }
#         ],
#         'Tags': [
#             {'Key': 'Owner', 'Value': user_email},
#             {'Key': 'Name', 'Value': identifier},
#             {'Key': 'Application', 'Value': spark_job_provisioner.config['INSTANCE_APP_TAG']},
#             {'Key': 'App', 'Value': spark_job_provisioner.config['ACCOUNTING_APP_TAG']},
#             {'Key': 'Type', 'Value': spark_job_provisioner.config['ACCOUNTING_TYPE_TAG']},
#         ],
#         'VisibleToAllUsers': True,
#     }
#     stubber.add_response('run_job_flow', response, expected_params)
#
#     with stubber:
#         jobflow_id = spark_job_provisioner.run(
#             user_email=user_email,
#             identifier=identifier,
#             emr_release=emr_release,
#             size=size,
#             notebook_key=notebook_key,
#             is_public=is_public,
#             job_timeout=job_timeout,
#         )
#         assert jobflow_id == '12345'
