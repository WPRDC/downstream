from django.db import models

class DownloadLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    resource_id = models.CharField(max_length=37, verbose_name='resource ID', blank=False, null=False)
    resource_name = models.CharField(max_length=200, blank=True, null=True)
    package_id = models.CharField(max_length=37, verbose_name='package ID', blank=True, null=True)
    package_name = models.CharField(max_length=150, blank=True, null=True)
    resource_format = models.CharField(max_length=20, blank=True, null=True)
    requested_file_format = models.CharField(max_length=20, blank=True, null=True)
    host = models.CharField(max_length=50, blank=True, null=True)
    referrer = models.CharField(max_length=50, blank=True, null=True)
    user_agent = models.CharField(max_length=200, blank=True, null=True)
    ip_address = models.CharField(max_length=20, verbose_name="IP address", blank=True, null=True)
    remote_host = models.CharField(max_length=50, blank=True, null=True)
    server_name = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return '{}: {}'.format(self.timestamp, self.resource_id)
