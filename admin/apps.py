from django.apps import AppConfig


class ProjectAdminConfig(AppConfig):
    # Give the custom admin app a unique label so it can coexist with django.contrib.admin.
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'admin'
    label = 'project_admin'
    verbose_name = 'Project Admin'