from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    MFASetupView,
    MFAVerifyView,
    UserProfileView,
    ArticleListView,
    ArticleDetailView,
    CommentListView,
    CategoryListView,
    TagListView,
    NotificationListView
)

urlpatterns = [
    # Autenticación
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('mfa/setup/', MFASetupView.as_view(), name='mfa-setup'),
    path('mfa/verify/', MFAVerifyView.as_view(), name='mfa-verify'),
    path('profile/', UserProfileView.as_view(), name='profile'),

    # Blog
    path('articles/', ArticleListView.as_view(), name='article-list'),
    path('articles/<int:pk>/', ArticleDetailView.as_view(), name='article-detail'),
    path('articles/<int:article_id>/comments/', CommentListView.as_view(), name='comment-list'),
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('tags/', TagListView.as_view(), name='tag-list'),
    path('notifications/', NotificationListView.as_view(), name='notification-list'),
]