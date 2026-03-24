from django.contrib.auth import login
from django.shortcuts import render

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .permissions import role_required
from .serializers import CustomTokenObtainPairSerializer, RegisterSerializer

class RegisterView(generics.CreateAPIView):
    # This API endpoint powers the signup form.
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginTokenView(APIView):
    # This API endpoint now does two jobs: it returns JWT tokens and creates a Django session.
    permission_classes = [permissions.AllowAny]
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        # Validate credentials with the same SimpleJWT serializer used earlier.
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create a normal Django session cookie so server-rendered pages can trust request.user.
        login(request, serializer.user)

        return Response(serializer.validated_data, status=status.HTTP_200_OK)

def index_view(request):
    # Public landing page.
    return render(request, "index.html")


def login_view(request):
    # Render the browser login page on GET. The form JavaScript calls the API endpoint separately.
    return render(request, "login.html")


def signup_view(request):
    # Render the browser signup page on GET. The form JavaScript calls the API endpoint separately.
    return render(request, "account_signup.html")


@role_required('admin')
def admin_home(request):
    # Only admins should be able to load the admin landing page.
    return render(request, 'admin.html')

