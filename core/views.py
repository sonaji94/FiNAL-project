from django.views.generic import TemplateView, DetailView, FormView, CreateView, ListView
from django.contrib.auth import login
from django.core.mail import send_mail

from django.contrib.auth.views import LoginView as AuthLoginView
from django.contrib.sites.models import Site
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.conf import settings
from django.db.models import Sum, Count
from django.db.utils import OperationalError, ProgrammingError
from accounts.models import User
from donations.models import Donation
from campaigns.models import Campaign, Category, CampaignProof
from campaigns.forms import CampaignForm, CampaignProofForm
from .models import SupportTicket
from .forms import SupportTicketForm
from accounts.forms import CustomUserCreationForm, CustomAuthenticationForm, OTPForgotPasswordForm, OTPVerifyForm, SetNewPasswordForm
import random
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages


def ensure_default_site(request=None):
    host = '127.0.0.1:8000'
    if request is not None:
        try:
            host = request.get_host() or host
        except Exception:
            pass

    try:
        Site.objects.update_or_create(
            id=settings.SITE_ID,
            defaults={
                'domain': host,
                'name': 'All-in-One Donation Platform',
            },
        )
    except (OperationalError, ProgrammingError):
        pass


class HomeView(TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['trending_campaigns'] = Campaign.objects.filter(
            status=Campaign.Status.ACTIVE, approved=True
        ).order_by('-raised_amount')[:3]
        context['categories'] = Category.objects.all()[:4]
        return context

class CategoryListView(ListView):
    model = Category
    template_name = 'category_list.html'
    context_object_name = 'categories'

class AboutView(TemplateView):
    template_name = 'about.html'

class CategoryDetailView(DetailView):
    model = Category
    template_name = 'category_detail.html'
    context_object_name = 'category'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['campaigns'] = self.object.campaigns.filter(
            status=Campaign.Status.ACTIVE,
            approved=True
        ).order_by('-raised_amount')
        context['all_categories'] = Category.objects.all()[:4] # Consistent with home page
        return context

class LoginView(AuthLoginView):
    template_name = 'login.html'
    authentication_form = CustomAuthenticationForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        ensure_default_site(request)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        user = self.request.user
        if user.is_superuser or user.is_admin_role():
            return reverse_lazy('admin_dashboard')
        return reverse_lazy('dashboard')

class RegisterView(CreateView):
    template_name = 'register.html'
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        user = form.save(commit=False)
        if not user.username:
            # Generate username from email (take everything before @)
            base_username = user.email.split('@')[0]
            user.username = base_username
            
            # Check for name collisions and append random numbers if necessary
            count = 1
            while User.objects.filter(username=user.username).exists():
                user.username = f"{base_username}{count}"
                count += 1
                
        user.save()
        login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect(self.success_url)

    def dispatch(self, request, *args, **kwargs):
        ensure_default_site(request)
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

class BaseDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['my_campaigns'] = Campaign.objects.filter(owner=user)
        
        # Admins see ALL platform transactions; regular users see only their own
        if user.is_superuser or user.is_admin_role():
            context['my_donations'] = Donation.objects.select_related('donor', 'campaign').order_by('-created_at')
            context['is_admin_donations_view'] = True
        else:
            context['my_donations'] = Donation.objects.filter(
                donor=user, 
                status=Donation.Status.SUCCESS
            ).order_by('-created_at')
            context['is_admin_donations_view'] = False
        return context

class DashboardView(BaseDashboardView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'campaigns'
        return context

class MyDonationsView(BaseDashboardView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'donations'
        return context

class MyTicketsView(BaseDashboardView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'tickets'
        context['support_tickets'] = SupportTicket.objects.filter(user=self.request.user)
        context['ticket_form'] = SupportTicketForm()
        return context

class RaiseTicketView(LoginRequiredMixin, CreateView):
    model = SupportTicket
    form_class = SupportTicketForm
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        ticket = form.save()
        messages.success(self.request, f"Ticket {ticket.ticket_id} has been raised successfully! Our team will review it shortly.")
        return redirect('my_tickets')
    
    def form_invalid(self, form):
        messages.error(self.request, "There was an error raising your ticket. Please check the details and try again.")
        return redirect('my_tickets')

class AccountSettingsView(BaseDashboardView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'settings'
        return context

class CampaignDetailView(DetailView):
    model = Campaign
    template_name = 'campaign_detail.html'
    context_object_name = 'campaign'

class CreateCampaignView(LoginRequiredMixin, CreateView):
    model = Campaign
    form_class = CampaignForm
    template_name = 'create_campaign.html'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['proof_form'] = CampaignProofForm(self.request.POST, self.request.FILES, prefix='proof')
        else:
            data['proof_form'] = CampaignProofForm(prefix='proof')
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        proof_form = context['proof_form']

        if form.is_valid() and proof_form.is_valid():
            form.instance.owner = self.request.user
            self.object = form.save()

            # Save the proof
            proof = proof_form.save(commit=False)
            if proof.document:  # Only save if a document was actually uploaded
                proof.campaign = self.object
                proof.save()

            messages.success(
                self.request,
                f"Campaign '{self.object.title}' has been submitted and sent to the admin team for review.",
            )
            return redirect('campaign_detail', pk=self.object.pk)
        return self.render_to_response(self.get_context_data(form=form))

class AdminDashboardView(UserPassesTestMixin, TemplateView):
    template_name = 'admin/dashboard.html'

    def test_func(self):
        return self.request.user.is_authenticated and (self.request.user.is_admin_role() or self.request.user.is_superuser)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Calculate totals
        context['total_collected'] = Campaign.objects.aggregate(total=Sum('raised_amount'))['total'] or 0
        context['total_campaigns'] = Campaign.objects.count()
        context['total_users'] = User.objects.count()
        
        context['seekers'] = User.objects.filter(campaigns__isnull=False).distinct().annotate(
            total_raised=Sum('campaigns__raised_amount'),
            campaign_count=Count('campaigns')
        ).prefetch_related('campaigns', 'campaigns__proofs').order_by('-total_raised')
        
        # Support Tickets
        ticket_queryset = SupportTicket.objects.select_related('user').order_by('-updated_at', '-created_at')
        hidden_ticket_ids = self.request.session.get('hidden_resolved_ticket_ids', [])

        context['support_tickets'] = ticket_queryset
        context['open_tickets'] = ticket_queryset.exclude(
            status__in=[SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED]
        )

        resolved_tickets = ticket_queryset.filter(
            status__in=[SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED]
        )
        if hidden_ticket_ids:
            resolved_tickets = resolved_tickets.exclude(pk__in=hidden_ticket_ids)

        context['resolved_tickets'] = resolved_tickets
        context['total_open_tickets'] = context['open_tickets'].count()
        
        # Pending Campaign Applications
        context['pending_campaigns'] = Campaign.objects.filter(status=Campaign.Status.PENDING).select_related('owner', 'category').order_by('-created_at')
        context['total_pending_campaigns'] = context['pending_campaigns'].count()
        
        # All Donations (Transaction History)
        context['all_donations'] = Donation.objects.select_related('campaign', 'donor').order_by('-created_at')
        
        return context

class ResolveTicketView(UserPassesTestMixin, TemplateView):
    def test_func(self):
        return self.request.user.is_authenticated and (self.request.user.is_admin_role() or self.request.user.is_superuser)

    def post(self, request, pk):
        try:
            ticket = SupportTicket.objects.get(pk=pk)
            requested_status = request.POST.get('status', SupportTicket.Status.RESOLVED)
            allowed_statuses = set(SupportTicket.Status.values)
            ticket.status = requested_status if requested_status in allowed_statuses else SupportTicket.Status.RESOLVED

            admin_notes = request.POST.get('admin_notes', '').strip()
            if ticket.status == SupportTicket.Status.RESOLVED and not admin_notes:
                admin_notes = 'The support team reviewed this ticket and marked it as resolved.'
            ticket.admin_notes = admin_notes
            ticket.save()

            hidden_ticket_ids = request.session.get('hidden_resolved_ticket_ids', [])
            hidden_ticket_ids = [ticket_id for ticket_id in hidden_ticket_ids if ticket_id != ticket.pk]

            if ticket.status in [SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED]:
                hidden_ticket_ids.append(ticket.pk)

            if hidden_ticket_ids:
                request.session['hidden_resolved_ticket_ids'] = hidden_ticket_ids
            else:
                request.session.pop('hidden_resolved_ticket_ids', None)

            messages.success(
                request,
                f"Ticket {ticket.ticket_id} was updated to {ticket.get_status_display()} successfully.",
            )
        except SupportTicket.DoesNotExist:
            messages.error(request, "Ticket not found.")

        return redirect('admin_dashboard')

class ApproveCampaignView(UserPassesTestMixin, TemplateView):
    def test_func(self):
        return self.request.user.is_authenticated and (self.request.user.is_admin_role() or self.request.user.is_superuser)

    def post(self, request, pk):
        try:
            campaign = Campaign.objects.get(pk=pk)
            campaign.status = Campaign.Status.ACTIVE
            campaign.approved = True
            campaign.status_reason = ''
            campaign.save()
            messages.success(request, f"Campaign '{campaign.title}' has been approved and is now live!")
        except Campaign.DoesNotExist:
            messages.error(request, "Campaign not found.")
        return redirect('admin_dashboard')

class RejectCampaignView(UserPassesTestMixin, TemplateView):
    def test_func(self):
        return self.request.user.is_authenticated and (self.request.user.is_admin_role() or self.request.user.is_superuser)

    def post(self, request, pk):
        try:
            campaign = Campaign.objects.get(pk=pk)
            reason = request.POST.get('reason', 'Application rejected by admin.')
            campaign.status = Campaign.Status.REJECTED
            campaign.approved = False
            campaign.status_reason = reason
            campaign.save()
            messages.warning(request, f"Campaign '{campaign.title}' has been rejected.")
        except Campaign.DoesNotExist:
            messages.error(request, "Campaign not found.")
        return redirect('admin_dashboard')

class ForgotPasswordRequestView(FormView):
    template_name = 'accounts/password_reset_request.html'
    form_class = OTPForgotPasswordForm
    success_url = reverse_lazy('password_reset_verify')

    def form_valid(self, form):
        email = form.cleaned_data['email']
        try:
            user = User.objects.get(email=email)
            
            # Generate 6-digit OTP
            otp = str(random.randint(100000, 999999))
            user.otp_code = otp
            user.otp_expiry = timezone.now() + timedelta(minutes=10)
            user.save()

            # SEND ACTUAL EMAIL
            subject = 'Password Reset OTP - EduNet NextGen'
            message = f'Your OTP for password reset is: {otp}. It is valid for 10 minutes.'
            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [email]
            
            try:
                # Use fail_silently=False to catch errors
                send_mail(subject, message, from_email, recipient_list, fail_silently=False)
                messages.success(self.request, f"OTP sent to your email ({email}).")
            except Exception as e:
                print(f"ERROR: Email delivery failed. Check .env credentials: {e}")
                messages.error(self.request, f"Email delivery failed! Please check your SMTP settings in .env.")
            
            # This MUST be set for the verification step to identify the user
            self.request.session['reset_email'] = email
            return super().form_valid(form)
        except User.DoesNotExist:
            form.add_error('email', "No user found with this email address.")
            return self.form_invalid(form)

class ForgotPasswordVerifyView(FormView):
    template_name = 'accounts/password_reset_verify.html'
    form_class = OTPVerifyForm
    success_url = reverse_lazy('password_reset_confirm')

    def form_valid(self, form):
        otp = form.cleaned_data['otp_code']
        email = self.request.session.get('reset_email')
        
        if not email:
            return redirect('password_reset_request')
        
        try:
            user = User.objects.get(email=email)
            if user.otp_code == otp and user.otp_expiry > timezone.now():
                user.otp_code = None # Clear OTP after verification
                user.save()
                return super().form_valid(form)
            else:
                form.add_error('otp_code', "Invalid or expired OTP.")
                return self.form_invalid(form)
        except User.DoesNotExist:
            return redirect('password_reset_request')

class ForgotPasswordResetView(FormView):
    template_name = 'accounts/password_reset_confirm.html'
    form_class = SetNewPasswordForm
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        email = self.request.session.get('reset_email')
        if not email:
            return redirect('password_reset_request')
        
        try:
            user = User.objects.get(email=email)
            user.set_password(form.cleaned_data['new_password'])
            user.save()
            
            del self.request.session['reset_email']
            messages.success(self.request, "Password reset successful. You can now log in with your new password.")
            return super().form_valid(form)
        except User.DoesNotExist:
            return redirect('password_reset_request')
