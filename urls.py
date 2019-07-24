from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^(?P<resource_id>[^/]+)$', views.stream_response, name='stream_response'),
    url(r'^(?P<resource_id>[^/]+)/(?P<file_format>[^/]+)$', views.stream_response, name='stream_by_file_format'),
    ]
