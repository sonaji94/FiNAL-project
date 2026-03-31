from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import HomeView, LoginView, RegisterView, AboutView, DashboardView, AdminDashboardView, CampaignDetailView, CreateCampaignView, CategoryDetailView, CategoryListView, ForgotPasswordRequestView, ForgotPasswordVerifyView, ForgotPasswordResetView, MyDonationsView, MyTicketsView, RaiseTicketView, AccountSettingsView, ResolveTicketView, ApproveCampaignView, RejectCampaignView

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('about/', AboutView.as_view(), name='about'),
    path('login/', LoginView.as_view(), name='login'),
    path('register/', RegisterView.as_view(), name='register'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('dashboard/donations/', MyDonationsView.as_view(), name='my_donations'),
    path('dashboard/tickets/', MyTicketsView.as_view(), name='my_tickets'),
    path('dashboard/tickets/raise/', RaiseTicketView.as_view(), name='raise_ticket'),
    path('dashboard/account/', AccountSettingsView.as_view(), name='account_settings'),
    path('categories/', CategoryListView.as_view(), name='category_list'),
    path('campaign/<int:pk>/', CampaignDetailView.as_view(), name='campaign_detail'),
    path('campaign/new/', CreateCampaignView.as_view(), name='create_campaign'),
    path('category/<slug:slug>/', CategoryDetailView.as_view(), name='category_detail'),
    path('admin-dashboard/', AdminDashboardView.as_view(), name='admin_dashboard'),
    path('admin-dashboard/resolve-ticket/<int:pk>/', ResolveTicketView.as_view(), name='resolve_ticket'),
    path('admin-dashboard/approve-campaign/<int:pk>/', ApproveCampaignView.as_view(), name='approve_campaign'),
    path('admin-dashboard/reject-campaign/<int:pk>/', RejectCampaignView.as_view(), name='reject_campaign'),
    path('logout/', LogoutView.as_view(next_page='home'), name='logout'),
    # Password Reset
    path('password_reset/', ForgotPasswordRequestView.as_view(), name='password_reset_request'),
    path('password_reset/verify/', ForgotPasswordVerifyView.as_view(), name='password_reset_verify'),
    path('password_reset/confirm/', ForgotPasswordResetView.as_view(), name='password_reset_confirm'),

]
