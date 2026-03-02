from django.shortcuts import render

from rest_framework import generics
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import RegisterSerializer
from .models import User

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer

from rest_framework.views import APIView
from rest_framework.response import Response
from .permissions import IsBuyer, IsSeller, IsAdmin

class BuyerView(APIView):
    permission_classes = [IsBuyer]

    def get(self, request):
        return Response({"message": "Test Buyer"})


class SellerView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        return Response({"message": "Test Seller"})


class AdminView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({"message": "Test Admin"})
