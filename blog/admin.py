from django.contrib import admin #추가
from blog.models import Post, Comment #추가


# 아래 모두 추가
@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    pass

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    pass