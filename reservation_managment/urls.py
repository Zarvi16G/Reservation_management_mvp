from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('accounts/signup/', views.signup, name='signup'),
    # Django's login, with a limit on failed attempts (views.LoginView).
    path('accounts/login/', views.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/profile/', views.profile, name='profile'),
    # Email verification: the link sent at sign-up (or after changing the email).
    path('accounts/verify/resend/', views.resend_verification, name='resend_verification'),
    path('accounts/verify/<str:token>/', views.verify_email, name='verify_email'),
    # Change the password (logged in). Django's views; templates in registration/.
    path(
        'accounts/password/change/',
        auth_views.PasswordChangeView.as_view(),
        name='password_change',
    ),
    path(
        'accounts/password/change/done/',
        auth_views.PasswordChangeDoneView.as_view(),
        name='password_change_done',
    ),
    # Forgot your password? Email -> one-time link (1 hour) -> new password.
    # The same message is shown whether the email exists or not.
    path('accounts/password/reset/', views.PasswordResetView.as_view(), name='password_reset'),
    path(
        'accounts/password/reset/sent/',
        auth_views.PasswordResetDoneView.as_view(),
        name='password_reset_done',
    ),
    path(
        'accounts/password/reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(),
        name='password_reset_confirm',
    ),
    path(
        'accounts/password/reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(),
        name='password_reset_complete',
    ),
    # Booking: slot picker -> checkout -> pay (result shown back on the picker).
    path('bookings/new/', views.book, name='book'),
    path('bookings/checkout/', views.checkout, name='book_checkout'),
    path('bookings/pay/', views.pay, name='book_pay'),
    path('bookings/customers/', views.customer_search, name='customer_search'),
    # The logged-in user's own bookings.
    path('bookings/', views.my_bookings, name='my_bookings'),
    path('bookings/<int:pk>/cancel/', views.cancel_booking, name='cancel_booking'),
    path('bookings/<int:pk>/reschedule/', views.reschedule_booking, name='reschedule_booking'),
]
