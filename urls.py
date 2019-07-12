from django.conf.urls import url

from . import views

urlpatterns = [
    #url(r'^$', views.index, name='index'),
    url(r'^(?P<resource_id>[^/]+)$', views.stream_response, name='stream_response'),
    url(r'^(?P<resource_id>[^/]+)/csv$', views.stream_csv, name='stream_csv'),
    ]
