from django.core import exceptions
from django.db import models
from rest_framework import serializers
from django.db.models import F, Sum
from django.contrib.auth.models import User
from cart.models import Product, Order, OrderDetail
from cart.services.order import OrderService


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class ProductSerializer(serializers.ModelSerializer):

    class Meta:
        model = Product
        fields = ['id', 'name', 'code', 'slug',
                  'price', 'get_image', 'get_thumbnail']


class OrderDetailSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(
        read_only=True, default=serializers.CurrentUserDefault())
    product_id = serializers.UUIDField(required=False)

    class Meta:
        model = OrderDetail
        fields = ['quantity', 'product_id', 'user']

    def validate(self, data):
        if 'quantity' not in data:
            raise serializers.ValidationError("quantity is required")
        if data['quantity'] < 1:
            raise serializers.ValidationError("quantity is less than 1")
        return data

    def create(self, validated_data):
        product_id = self.context['request'].data.get('product_id')
        user = self.context.get('request', None).user
        quantity = validated_data['quantity']
        product = Product.objects.filter(pk=product_id).first()
        if not product:
            raise serializers.ValidationError('Product not found')
        order_id = Order.objects.filter(
            customer_id=user.id, complete=False).values_list('id', flat=True).last()
        order, created = Order.objects.get_or_create(
            pk=order_id, customer_id=user)
        if order:
            orderdetail = OrderDetail.objects.filter(
                product=product, order=order).first()
            if orderdetail:
                orderdetail.quantity += quantity
                orderdetail.price = product.price
                orderdetail.save()
            else:
                orderdetail = OrderDetail.objects.create(
                    product=product, order=order, quantity=quantity, price=product.price
                )
            total = sum(
                (item.get_total for item in OrderDetail.objects.filter(order=order) if item))
            order.total = total
            order.save()
        return orderdetail


class BuyProductSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField()
    quantity = serializers.IntegerField(default=1)
    price = serializers.DecimalField(max_digits=11, decimal_places=2)

    class Meta:
        model = Product
        fields = ['id', 'quantity', 'price']


class OrderSerializer(serializers.ModelSerializer):
    order_detail = OrderDetailSerializer(many=True, required=False)
    products = BuyProductSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = Order
        fields = ['id', 'total', 'order_detail', 'products']

    def update(self, instance, validated_data):
        products = self.context['request'].data.get('products')
        product_ids = [product.get('id') for product in products if product]
        if product_ids == []:
            OrderDetail.objects.filter(order=instance).delete()
            return super().update(instance, validated_data)
        OrderService.addProductToOrder(instance, product_ids, products)
        return super().update(instance, validated_data)
