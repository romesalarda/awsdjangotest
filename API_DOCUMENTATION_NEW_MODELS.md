# API Documentation: New Models Implementation

## Overview
This document describes the newly created serializers and viewsets for the following models:
- `DonationPayment` (in payment_models.py)
- `Organisation` (in organisation_models.py)
- `OrganisationSocialMediaLink` (in organisation_models.py)

## File Structure

### Created Files
1. **`apps/events/api/serializers/organisation_serializers.py`** - Organisation serializers
2. **`apps/events/api/views/organisation_viewsets.py`** - Organisation viewsets

### Modified Files
1. **`apps/events/api/serializers/payment_serializers.py`** - Added DonationPayment serializers
2. **`apps/events/api/views/payment_viewsets.py`** - Added DonationPayment viewset
3. **`apps/events/api/serializers/__init__.py`** - Added organisation serializers import
4. **`apps/events/api/views/__init__.py`** - Added organisation viewsets import
5. **`apps/events/api/urls.py`** - Added organisation router and donations endpoint
6. **`core/urls.py`** - Added organisation API route

---

## 1. DonationPayment API

### Endpoints
- `GET /api/events/payments/donations/` - List all donations
- `POST /api/events/payments/donations/` - Create a new donation
- `GET /api/events/payments/donations/{id}/` - Get donation details
- `PUT/PATCH /api/events/payments/donations/{id}/` - Update donation
- `DELETE /api/events/payments/donations/{id}/` - Delete donation (admin only)
- `POST /api/events/payments/donations/{id}/mark-paid/` - Mark donation as paid (admin only)
- `GET /api/events/payments/donations/statistics/` - Get donation statistics
- `GET /api/events/payments/donations/by-event/{event_id}/` - Get donations by event

### Serializers

#### `DonationPaymentSerializer`
Full-featured serializer with all donation fields and computed properties.

**Fields:**
- `id` (read-only, UUID)
- `user` (EventParticipant UUID)
- `participant_details` (read-only, nested participant info)
- `participant_user_email` (read-only)
- `event` (Event UUID)
- `event_name` (read-only)
- `method` (EventPaymentMethod ID)
- `method_display` (read-only)
- `stripe_payment_intent`
- `amount` (Decimal)
- `amount_display` (read-only, formatted)
- `currency` (default: "gbp")
- `status` (choices: PENDING, SUCCEEDED, FAILED)
- `status_display` (read-only)
- `event_payment_tracking_number`
- `bank_reference`
- `paid_at` (DateTime, nullable)
- `created_at` (read-only)
- `updated_at` (read-only)

**Features:**
- Automatic event assignment from participant
- Validation: participant must belong to event
- Validation: amount must be positive
- Auto-update paid_at when status changes to SUCCEEDED

#### `DonationPaymentListSerializer`
Lightweight serializer for list views.

**Additional Fields:**
- `participant_id`, `participant_name`, `participant_email`
- `participant_event_pax_id`
- `payment_method`, `payment_method_type`

### ViewSet: `DonationPaymentViewSet`

**Permissions:**
- Authenticated users: List, Create, Retrieve
- Admin users: Update, Delete, mark-paid

**Query Filters:**
- `event` - Filter by event ID
- `participant` - Filter by participant ID
- `status` - Filter by payment status
- `method` - Filter by payment method ID
- `date_from` - Filter by creation date (from)
- `date_to` - Filter by creation date (to)

**Custom Actions:**

##### `POST /donations/{id}/mark-paid/`
Marks a donation as paid (admin only).
- Sets status to SUCCEEDED
- Sets paid_at timestamp
- Returns updated donation data

##### `GET /donations/statistics/`
Returns donation statistics:
- Total donations count
- Total amount donated
- Statistics by status
- Statistics by event (top 10)
- Recent donations (last 5)

##### `GET /donations/by-event/{event_id}/`
Returns all donations for a specific event with event statistics.

---

## 2. Organisation API

### Endpoints
- `GET /api/organisations/organisations/` - List all organisations
- `POST /api/organisations/organisations/` - Create organisation (admin only)
- `GET /api/organisations/organisations/{id}/` - Get organisation details
- `PUT/PATCH /api/organisations/organisations/{id}/` - Update organisation (admin only)
- `DELETE /api/organisations/organisations/{id}/` - Delete organisation (admin only)
- `GET /api/organisations/organisations/{id}/social-media/` - Get social media links
- `POST /api/organisations/organisations/{id}/add-social-media/` - Add social media link (admin only)
- `DELETE /api/organisations/organisations/{id}/remove-social-media/{link_id}/` - Remove link (admin only)
- `GET /api/organisations/organisations/statistics/` - Get organisation statistics

### Serializers

#### `OrganisationSerializer`
Full-featured serializer with nested social media link creation.

**Fields:**
- `id` (read-only, UUID)
- `name`
- `description`
- `landing_image` (ImageField)
- `landing_image_url` (read-only, full URL)
- `logo` (ImageField)
- `logo_url` (read-only, full URL)
- `email`
- `external_link`
- `social_media_links` (read-only, nested)
- `social_media_data` (write-only, for creation)
- `social_media_count` (read-only)

**Features:**
- Nested social media link creation/update
- Email validation
- External link URL validation
- Full URL generation for images

**Example Create Request:**
```json
{
  "name": "ANCOP International",
  "description": "Answering the Cry of the Poor",
  "email": "contact@ancop.org",
  "external_link": "https://www.ancop.org",
  "social_media_data": [
    {
      "name": "Facebook",
      "external_link": "https://facebook.com/ancop",
      "description": "Official page"
    }
  ]
}
```

#### `OrganisationListSerializer`
Lightweight serializer for list views with essential fields only.

#### `OrganisationSocialMediaLinkSerializer`
Serializer for social media links.

**Fields:**
- `id` (read-only, UUID)
- `name` (e.g., "Facebook", "Instagram")
- `external_link`
- `description`
- `organisation` (Organisation UUID)

**Features:**
- URL validation (must start with http:// or https://)

#### `OrganisationSocialMediaLinkCreateSerializer`
Simplified serializer for nested creation (organisation field auto-set).

### ViewSet: `OrganisationViewSet`

**Permissions:**
- Read operations: Authenticated or read-only
- Create/Update/Delete: Admin only

**Query Filters:**
- `search` - Search in name and description
- `has_logo` - Filter by logo presence (true/false)
- `has_social_media` - Filter by social media link presence (true/false)

**Custom Actions:**

##### `GET /organisations/{id}/social-media/`
Returns all social media links for an organisation.

##### `POST /organisations/{id}/add-social-media/`
Adds a new social media link to an organisation (admin only).

**Request:**
```json
{
  "name": "Twitter",
  "external_link": "https://twitter.com/org",
  "description": "Official Twitter"
}
```

##### `DELETE /organisations/{id}/remove-social-media/{link_id}/`
Removes a social media link (admin only).

##### `GET /organisations/statistics/`
Returns organisation statistics:
- Total organisations count
- Organisations with logos
- Organisations with social media
- Total social media links
- Average social links per organisation

---

## 3. OrganisationSocialMediaLink API

### Endpoints
- `GET /api/organisations/social-media-links/` - List all social media links
- `POST /api/organisations/social-media-links/` - Create link (admin only)
- `GET /api/organisations/social-media-links/{id}/` - Get link details
- `PUT/PATCH /api/organisations/social-media-links/{id}/` - Update link (admin only)
- `DELETE /api/organisations/social-media-links/{id}/` - Delete link (admin only)
- `GET /api/organisations/social-media-links/by-platform/{platform}/` - Get links by platform

### ViewSet: `OrganisationSocialMediaLinkViewSet`

**Permissions:**
- Read operations: Authenticated or read-only
- Create/Update/Delete: Admin only

**Query Filters:**
- `organisation` - Filter by organisation ID
- `name` - Filter by platform name

**Custom Actions:**

##### `GET /social-media-links/by-platform/{platform_name}/`
Returns all social media links for a specific platform.

---

## Testing Examples

### Create a Donation
```bash
POST /api/events/payments/donations/
{
  "user": "123e4567-e89b-12d3-a456-426614174000",
  "event": "456e7890-e89b-12d3-a456-426614174001",
  "method": 2,
  "amount": 25.00,
  "currency": "gbp",
  "status": "PENDING"
}
```

### Create an Organisation with Social Media
```bash
POST /api/organisations/organisations/
{
  "name": "ANCOP International",
  "description": "Serving the poor",
  "email": "contact@ancop.org",
  "external_link": "https://www.ancop.org",
  "social_media_data": [
    {
      "name": "Facebook",
      "external_link": "https://facebook.com/ancop"
    }
  ]
}
```

### Get Donation Statistics
```bash
GET /api/events/payments/donations/statistics/
```

### Filter Donations by Event
```bash
GET /api/events/payments/donations/?event=456e7890-e89b-12d3-a456-426614174001
```

### Search Organisations
```bash
GET /api/organisations/organisations/?search=ANCOP
```

---

## Summary

All three models now have:
✅ **Full CRUD operations** (Create, Read, Update, Delete)
✅ **Detailed serializers** with nested data support
✅ **List serializers** for optimized list views
✅ **Comprehensive documentation** in docstrings
✅ **Query filtering** for flexible data retrieval
✅ **Custom actions** for specific business logic
✅ **Proper permissions** (read-only public, admin for modifications)
✅ **Validation** for data integrity
✅ **Statistics endpoints** for reporting
✅ **Nested creation** support (Organisation with social media links)

The implementation follows Django REST Framework best practices and maintains consistency with the existing codebase patterns.
