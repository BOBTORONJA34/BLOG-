from rest_framework import generics, permissions, status, serializers, filters
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django_filters.rest_framework import DjangoFilterBackend
from .models import User, Article, Comment, Category, Tag, Notification
from .serializers import (
    UserSerializer,
    RegisterSerializer,
    LoginSerializer,
    MFASetupSerializer,
    MFAVerifySerializer,
    ArticleSerializer,
    CommentSerializer,
    CategorySerializer,
    TagSerializer,
    NotificationSerializer
)
import pyotp
import qrcode
import qrcode.image.svg
from io import BytesIO
from django.utils import timezone


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            "user": UserSerializer(user, context=self.get_serializer_context()).data,
            "message": "Usuario creado exitosamente",
        })


class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data

        if user.mfa_secret:
            return Response({
                "mfa_required": True,
                "temp_token": str(RefreshToken.for_user(user).access_token),
            })

        refresh = RefreshToken.for_user(user)
        return Response({
            "user": UserSerializer(user, context=self.get_serializer_context()).data,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        })


class MFASetupView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MFASetupSerializer

    def get(self, request, *args, **kwargs):
        user = request.user
        if user.mfa_secret:
            return Response({"detail": "MFA ya está configurado"}, status=status.HTTP_400_BAD_REQUEST)

        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name="Blog Colaborativo")

        factory = qrcode.image.svg.SvgImage
        img = qrcode.make(provisioning_uri, image_factory=factory)
        stream = BytesIO()
        img.save(stream)

        return Response({
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "qr_code": stream.getvalue().decode(),
        })

    def post(self, request, *args, **kwargs):
        user = request.user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)

        if not totp.verify(serializer.validated_data['code']):
            return Response({"detail": "Código inválido"}, status=status.HTTP_400_BAD_REQUEST)

        user.mfa_secret = secret
        user.save()

        return Response({"detail": "MFA configurado exitosamente"})


class MFAVerifyView(generics.GenericAPIView):
    serializer_class = MFAVerifySerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            jwt_auth = JWTAuthentication()
            user, _ = jwt_auth.authenticate(request)

            if not user:
                return Response({"detail": "Token inválido"}, status=status.HTTP_401_UNAUTHORIZED)

            totp = pyotp.TOTP(user.mfa_secret)
            if not totp.verify(serializer.validated_data['code']):
                return Response({"detail": "Código inválido"}, status=status.HTTP_400_BAD_REQUEST)

            refresh = RefreshToken.for_user(user)
            return Response({
                "user": UserSerializer(user, context=self.get_serializer_context()).data,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            })
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ArticleListView(generics.ListCreateAPIView):
    queryset = Article.objects.filter(is_published=True)
    serializer_class = ArticleSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['categories', 'tags', 'author']
    search_fields = ['title', 'content']
    ordering_fields = ['created_at', 'updated_at']

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class ArticleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_update(self, serializer):
        instance = serializer.save()
        Notification.objects.create(
            user=instance.author,
            message=f"Tu artículo '{instance.title}' ha sido actualizado",
            link=f"/articles/{instance.id}"
        )


class CommentListView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        article_id = self.kwargs['article_id']
        return Comment.objects.filter(article_id=article_id, parent_comment__isnull=True)

    def perform_create(self, serializer):
        article = Article.objects.get(pk=self.kwargs['article_id'])
        comment = serializer.save(article=article, author=self.request.user)

        if comment.author != article.author:
            Notification.objects.create(
                user=article.author,
                message=f"{comment.author.username} ha comentado tu artículo '{article.title}'",
                link=f"/articles/{article.id}#comment-{comment.id}"
            )

        if comment.parent_comment:
            Notification.objects.create(
                user=comment.parent_comment.author,
                message=f"{comment.author.username} ha respondido a tu comentario",
                link=f"/articles/{article.id}#comment-{comment.id}"
            )


class CategoryListView(generics.ListCreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class TagListView(generics.ListCreateAPIView):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')