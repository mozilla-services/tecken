# import io
# import uuid
#
# import pytest
# from cryptography.hazmat.backends import \
#     default_backend as crypto_default_backend
# from cryptography.hazmat.primitives import \
#     serialization as crypto_serialization
# from cryptography.hazmat.primitives.asymmetric import rsa
# from django.core.files.uploadedfile import InMemoryUploadedFile
# from django.utils import timezone
#
# from atmo.clusters.provisioners import ClusterProvisioner
# from atmo.jobs.provisioners import SparkJobProvisioner
# from atmo.keys.models import SSHKey
#
# pytest_plugins = ['blockade']
#
#
# @pytest.fixture
# def now():
#     return timezone.now()
#
#
# @pytest.fixture
# def test_user(client, django_user_model):
#     test_user = django_user_model.objects.create_user(
#         'testuser',
#         'test@example.com',
#         'testpassword',
#     )
#     client.force_login(test_user)
#     return test_user
#
#
# @pytest.fixture
# def test_user2(client, django_user_model):
#     test_user = django_user_model.objects.create_user(
#         'testuser2',
#         'test2@example.com',
#         'testpassword2',
#     )
#     return test_user
#
#
# @pytest.fixture
# def notebook_maker():
#     def maker(extension='ipynb'):
#         return InMemoryUploadedFile(
#             file=io.BytesIO(b'{}'),
#             field_name='notebook',
#             name='test-notebook.%s' % extension,
#             content_type='text/plain',
#             size=2,
#             charset='utf8',
#         )
#     return maker
#
#
# @pytest.fixture
# def public_rsa_key_maker():
#     def maker():
#         key = rsa.generate_private_key(
#             backend=crypto_default_backend(),
#             public_exponent=65537,
#             key_size=2048
#         )
#         return key.public_key().public_bytes(
#             crypto_serialization.Encoding.OpenSSH,
#             crypto_serialization.PublicFormat.OpenSSH
#         ).decode('utf-8')
#     return maker
#
#
# @pytest.fixture
# def ssh_key(test_user, public_rsa_key_maker):
#     return SSHKey.objects.create(
#         title=uuid.uuid4().hex,
#         key=public_rsa_key_maker(),
#         created_by=test_user,
#     )
#
#
# @pytest.fixture
# def spark_job_provisioner():
#     return SparkJobProvisioner()
#
#
# @pytest.fixture
# def cluster_provisioner():
#     return ClusterProvisioner()
#
#
# @pytest.fixture(autouse=True)
# def patch_spark_emr_configuration(mocker):
#     mocker.patch(
#         'atmo.provisioners.Provisioner.spark_emr_configuration',
#         return_value=[
#             {
#                 'Classification': 'atmo-tests',
#                 'Properties': {
#                     'passing': 'of-course',
#                     'covering': 'everything',
#                 }
#             },
#         ]
#     )
#
#
# @pytest.fixture(autouse=True)
# def patch_google_auth_discovery_endpoint(mocker):
#     mocker.patch(
#         'atmo.users.views.AtmoGoogleOAuth2Adapter.discovery_document',
#         return_value={
#             'authorization_endpoint': 'https://accounts.google.com/o/oauth2/v2/auth',
#             'claims_supported': [
#                 'aud',
#                 'email',
#                 'email_verified',
#                 'exp',
#                 'family_name',
#                 'given_name',
#                 'iat',
#                 'iss',
#                 'locale',
#                 'name',
#                 'picture',
#                 'sub',
#             ],
#             'code_challenge_methods_supported': ['plain', 'S256'],
#             'id_token_signing_alg_values_supported': ['RS256'],
#             'issuer': 'https://accounts.google.com',
#             'jwks_uri': 'https://www.googleapis.com/oauth2/v3/certs',
#             'response_types_supported': [
#                 'code',
#                 'token',
#                 'id_token',
#                 'code token',
#                 'code id_token',
#                 'token id_token',
#                 'code token id_token',
#                 'none'
#             ],
#             'revocation_endpoint': 'https://accounts.google.com/o/oauth2/revoke',
#             'scopes_supported': ['openid', 'email', 'profile'],
#             'subject_types_supported': ['public'],
#             'token_endpoint': 'https://www.googleapis.com/oauth2/v4/token',
#             'token_endpoint_auth_methods_supported': [
#                 'client_secret_post',
#                 'client_secret_basic',
#             ],
#             'userinfo_endpoint': 'https://www.googleapis.com/oauth2/v3/userinfo',
#         }
#     )
