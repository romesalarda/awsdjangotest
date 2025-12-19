from django.contrib import admin
from apps.shop.models.payments import *
from apps.shop.models.metadata_models import *

@admin.register(ProductPaymentMethod)
class ProductPaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("method", "account_name", "is_active", "created_at")
    list_filter = ("method", "is_active")
    search_fields = ("method", "account_name", "account_number", "iban", "swift_bic")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

@admin.register(ProductPaymentPackage)
class ProductPaymentPackageAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "currency", "is_active", "available_from", "available_until")
    list_filter = ("is_active", "currency")
    search_fields = ("name", "description")
    filter_horizontal = ("products",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

@admin.register(ProductPayment)
class ProductPaymentAdmin(admin.ModelAdmin):
    list_display = ("user", "cart", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency", "created_at")
    search_fields = ("user__email", "cart__uuid", "stripe_payment_intent")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
    
@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("title", "description")
    search_fields = ("title", "description")
    ordering = ("title",)

@admin.register(ProductMaterial)
class ProductMaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "description")
    search_fields = ("title", "description")
    ordering = ("title",)

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("uuid", "product", "image")
    search_fields = ("product__title", "image")
    ordering = ("-uuid",)
    
class ProductSizeInline(admin.StackedInline):
    model = ProductSize
    extra = 0
    fields = ['size', 'quantity', 'price_modifier']
    readonly_fields = []
    
    def get_readonly_fields(self, request, obj=None):
        """Show warnings for low stock"""
        if obj and obj.quantity < 5:
            return ['low_stock_warning']
        return []
    
@admin.register(EventProduct)
class EventProductAdmin(admin.ModelAdmin):
    list_display = ("title", "event", "seller", "price", "discount", "uses_sizes", "stock_status", "total_stock")
    list_filter = ("event", "seller", "categories", "materials", "uses_sizes", "featured", "in_stock")
    search_fields = ("title", "description", "seller__email")
    filter_horizontal = ("categories", "materials")
    ordering = ("title",)
    inlines = [ProductSizeInline]
    
    def stock_status(self, obj):
        """Show stock status with color coding"""
        if obj.uses_sizes:
            total = obj.get_total_variant_stock()
            if total == 0:
                return "⚠️ Out of Stock (Variants)"
            elif total < 10:
                return f"🔶 Low ({total} total)"
            return f"✅ {total} total"
        else:
            if obj.stock == 0:
                return "∞ Infinite/Made-to-Order"
            elif obj.stock < 10:
                return f"🔶 Low ({obj.stock})"
            return f"✅ {obj.stock}"
    stock_status.short_description = "Stock Status"
    
    def total_stock(self, obj):
        """Show total stock across variants or product-level"""
        if obj.uses_sizes:
            return obj.get_total_variant_stock()
        return obj.stock if obj.stock > 0 else "∞"
    total_stock.short_description = "Total Available"



class EventProductOrderInline(admin.StackedInline):
    model = EventProductOrder
    extra = 0

@admin.register(EventCart)
class EventCartAdmin(admin.ModelAdmin):
    list_display = ("order_reference_id", "user", "event", "total", "shipping_cost", "approved", "submitted", "active", "cart_status")
    list_filter = ("approved", "submitted", "active", "event")
    search_fields = ("user__email", "event__name", "notes", "shipping_address")
    ordering = ("-created",)
    inlines = [EventProductOrderInline]

@admin.register(EventProductOrder)
class EventProductOrderAdmin(admin.ModelAdmin):
    list_display = ("product", "cart", "quantity", "added", "size", "discount_applied", "status")
    list_filter = ("status", "product", "cart")
    search_fields = ("product__title", "cart__user__email")
    ordering = ("-added",)
    readonly_fields = ("id",)
    
@admin.register(ProductSize)
class ProductSizeAdmin(admin.ModelAdmin):
    list_display = ("product", "size", "quantity", "price_modifier", "is_available", "stock_warning")
    list_filter = ("size", "product__event")
    search_fields = ("product__title",)
    ordering = ("product", "size")
    
    def is_available(self, obj):
        """Show availability status"""
        return "✅ Yes" if obj.is_available() else "❌ No"
    is_available.short_description = "Available"
    
    def stock_warning(self, obj):
        """Show warning for low stock"""
        if obj.quantity == 0:
            return "🚫 Out of Stock"
        elif obj.quantity < 5:
            return f"⚠️ Low Stock ({obj.quantity})"
        return "✅ OK"
    stock_warning.short_description = "Stock Status"
    
admin.site.register(ProductPaymentLog)
admin.site.register(OrderRefund)