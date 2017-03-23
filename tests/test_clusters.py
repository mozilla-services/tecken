# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from datetime import timedelta

import pytest
# from allauth.account.utils import user_display
# from django.contrib.messages import get_messages
# from django.core.urlresolvers import reverse
# from django.utils import timezone
#
# from atmo.clusters import models
#
#
# @pytest.fixture
# def cluster_provisioner_mocks(mocker):
#     return {
#         'start': mocker.patch(
#             'atmo.clusters.provisioners.ClusterProvisioner.start',
#             return_value='12345',
#         ),
#         'info': mocker.patch(
#             'atmo.clusters.provisioners.ClusterProvisioner.info',
#             return_value={
#                 'start_time': timezone.now(),
#                 'state': models.Cluster.STATUS_BOOTSTRAPPING,
#                 'state_change_reason_code': None,
#                 'state_change_reason_message': None,
#                 'public_dns': 'master.public.dns.name',
#             },
#         ),
#         'stop': mocker.patch(
#             'atmo.clusters.provisioners.ClusterProvisioner.stop',
#             return_value=None,
#         ),
#     }
#
#
# def test_cluster_form_defaults(client, test_user, ssh_key):
#     response = client.post(reverse('clusters-new'), {}, follow=True)
#
#     form = response.context['form']
#
#     assert form.errors
#     assert (form.initial['identifier'] ==
#             '{}-telemetry-analysis'.format(user_display(test_user)))
#     assert form.initial['size'] == 1
#     assert form.initial['ssh_key'] == ssh_key.id
#
#
# def test_no_keys_redirect(client, test_user):
#     response = client.post(reverse('clusters-new'), {}, follow=True)
#     assert response.status_code == 200
#     assert response.redirect_chain[-1] == (reverse('keys-new'), 302)
#     assert ('No SSH keys associated to you' in
#             [m for m in get_messages(response.wsgi_request)][0].message)
#
#
# def test_redirect_keys(client, test_user):
#     assert not test_user.created_sshkeys.exists()
#     response = client.get(reverse('clusters-new'), follow=True)
#     assert response.status_code == 200
#     assert response.redirect_chain[-1] == (reverse('keys-new'), 302)
#
#
# def test_create_cluster(client, test_user, ssh_key, cluster_provisioner_mocks):
#     start_date = timezone.now()
#
#     # request that a new cluster be created
#     response = client.post(
#         reverse('clusters-new'), {
#             'new-identifier': 'test-cluster',
#             'new-size': 5,
#             'new-ssh_key': ssh_key.id,
#             'new-emr_release': models.Cluster.EMR_RELEASES_CHOICES_DEFAULT,
#         }, follow=True)
#     cluster = models.Cluster.objects.get(jobflow_id='12345')
#
#     assert response.status_code == 200
#     assert response.redirect_chain[-1] == (cluster.get_absolute_url(), 302)
#
#     cluster_provisioner_mocks['start'].assert_called_with(
#         user_email='test@example.com',
#         identifier='test-cluster',
#         emr_release=models.Cluster.EMR_RELEASES_CHOICES_DEFAULT,
#         size=5,
#         public_key=ssh_key.key,
#     )
#
#     assert cluster.identifier == 'test-cluster'
#     assert cluster.size == 5
#     assert cluster.ssh_key == ssh_key
#     assert cluster.master_address == 'master.public.dns.name'
#     assert (
#         start_date <= cluster.start_date <= start_date + timedelta(seconds=10)
#     )
#     assert cluster.created_by == test_user
#     assert cluster.emr_release == models.Cluster.EMR_RELEASES_CHOICES_DEFAULT
#
#
# def test_empty_public_dns(client, cluster_provisioner_mocks, test_user, ssh_key):
#     cluster_provisioner_mocks['info'].return_value = {
#         'start_time': timezone.now(),
#         'state': models.Cluster.STATUS_BOOTSTRAPPING,
#         'public_dns': None,
#     }
#     new_url = reverse('clusters-new')
#
#     response = client.get(new_url)
#     assert response.status_code == 200
#     assert 'form' in response.context
#
#     new_data = {
#         'new-size': 5,
#         'new-ssh_key': ssh_key.id,
#         'new-emr_release': models.Cluster.EMR_RELEASES_CHOICES_DEFAULT
#     }
#
#     response = client.post(new_url, new_data, follow=True)
#     assert response.context['form'].errors
#
#     new_data.update({
#         'new-identifier': 'test-cluster',
#     })
#     response = client.post(new_url, new_data, follow=True)
#     assert cluster_provisioner_mocks['start'].call_count == 1
#     cluster = models.Cluster.objects.get(jobflow_id='12345')
#     assert cluster_provisioner_mocks['info'].call_count == 1
#     assert cluster.master_address == ''
#
#
# def test_terminate_cluster(client, cluster_provisioner_mocks, test_user,
#                            test_user2, ssh_key):
#
#     # create a test cluster to delete later
#     cluster = models.Cluster.objects.create(
#         identifier='test-cluster',
#         size=5,
#         ssh_key=ssh_key,
#         created_by=test_user,
#         jobflow_id='12345',
#         most_recent_status=models.Cluster.STATUS_BOOTSTRAPPING,
#     )
#     assert repr(cluster) == '<Cluster test-cluster of size 5>'
#
#     terminate_url = reverse('clusters-terminate', kwargs={'id': cluster.id})
#
#     response = client.get(terminate_url)
#     assert response.status_code == 200
#     assert 'cluster' in response.context
#
#     # setting state to TERMINATED so we can test the redirect to the detail page
#     cluster.most_recent_status = cluster.STATUS_TERMINATED
#     cluster.save()
#     response = client.get(terminate_url, follow=True)
#     assert response.status_code == 200
#     assert response.redirect_chain[-1] == (cluster.get_absolute_url(), 302)
#
#     # resettting to bootstrapping
#     cluster.most_recent_status = cluster.STATUS_BOOTSTRAPPING
#     cluster.save()
#
#     # login the second user so we can check the delete_cluster permission
#     client.force_login(test_user2)
#     response = client.get(terminate_url, follow=True)
#     assert response.status_code == 403
#
#     # force login the regular test user
#     client.force_login(test_user)
#
#     # request that the test cluster be terminated
#     response = client.post(terminate_url, follow=True)
#
#     assert response.status_code == 200
#     assert response.redirect_chain[-1] == (cluster.get_absolute_url(), 302)
#
#     cluster_provisioner_mocks['stop'].assert_called_with('12345')
#     assert models.Cluster.objects.filter(jobflow_id='12345').exists()
