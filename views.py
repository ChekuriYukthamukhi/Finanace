from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q, Avg
from django.db.models.functions import TruncMonth
from django.http import JsonResponse, HttpResponse, FileResponse
from django.utils import timezone
from django.core.cache import cache
from datetime import datetime, timedelta
import csv
import json
import io
from decimal import Decimal
import requests

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from .models import (
    Transaction, Category, Budget, SavingsGoal, Account, 
    RecurringTransaction, Notification, Wallet, Card, ExpenseSplit
)
from .forms import (
    TransactionForm, BudgetForm, SavingsGoalForm, AccountForm, 
    RecurringTransactionForm, WalletForm, CardForm
)

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            
            defaults = [
                {'name': 'Food', 'type': 'expense', 'icon': '🍕'},
                {'name': 'Transport', 'type': 'expense', 'icon': '🚗'},
                {'name': 'Shopping', 'type': 'expense', 'icon': '🛍️'},
                {'name': 'Bills', 'type': 'expense', 'icon': '📄'},
                {'name': 'Entertainment', 'type': 'expense', 'icon': '🎮'},
                {'name': 'Salary', 'type': 'income', 'icon': '💰'},
                {'name': 'Freelance', 'type': 'income', 'icon': '💻'},
                {'name': 'Rent', 'type': 'expense', 'icon': '🏠'},
                {'name': 'Healthcare', 'type': 'expense', 'icon': '🏥'},
                {'name': 'Education', 'type': 'expense', 'icon': '📚'},
            ]
            for cat in defaults:
                Category.objects.create(user=user, is_default=True, **cat)
            
            Account.objects.create(user=user, name='Cash', type='cash', balance=0)
            Wallet.objects.create(user=user, name='Main Wallet', balance=0, is_primary=True)
            
            messages.success(request, '🎉 Account created! Welcome to FinancePro 2.0!')
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})

@login_required
def dashboard(request):
    user = request.user
    cache_key = f'dashboard_{user.id}'
    data = cache.get(cache_key)
    
    if not data:
        transactions = Transaction.objects.filter(user=user)
        accounts = Account.objects.filter(user=user)
        budgets = Budget.objects.filter(user=user, is_active=True)
        goals = SavingsGoal.objects.filter(user=user)
        wallets = Wallet.objects.filter(user=user)
        
        total_balance = accounts.aggregate(Sum('balance'))['balance__sum'] or 0
        total_income = transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or 0
        total_expenses = transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Monthly data
        monthly_data = []
        today = timezone.now().date()
        for i in range(5, -1, -1):
            month = today.replace(day=1) - timedelta(days=30*i)
            month_start = month.replace(day=1)
            if i == 0:
                month_end = today
            else:
                next_month = month_start.replace(day=28) + timedelta(days=4)
                month_end = next_month - timedelta(days=next_month.day)
            
            m_trans = transactions.filter(date__gte=month_start, date__lte=month_end)
            monthly_data.append({
                'month': month_start.strftime('%b'),
                'income': float(m_trans.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or 0),
                'expenses': float(m_trans.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or 0)
            })
        
        # Category data
        category_data = {}
        for t in transactions.filter(type='expense')[:50]:
            cat_name = t.category.name if t.category else 'Uncategorized'
            category_data[cat_name] = category_data.get(cat_name, 0) + float(t.amount)
        
        # Budget progress
        budget_progress = []
        for budget in budgets[:5]:
            spent = budget.spent_amount()
            progress = budget.progress()
            status = budget.get_alert_status()
            budget_progress.append({
                'category': budget.category.name,
                'icon': budget.category.icon,
                'budgeted': float(budget.amount),
                'spent': float(spent),
                'remaining': float(budget.amount - spent),
                'progress': progress,
                'status': status[0],
                'alert': status[1],
                'message': status[2],
            })
        
        notifications = Notification.objects.filter(user=user, is_read=False)[:5]
        
        data = {
            'total_balance': total_balance,
            'total_income': total_income,
            'total_expenses': total_expenses,
            'accounts': accounts,
            'monthly_data': monthly_data,
            'category_data': category_data,
            'budget_progress': budget_progress,
            'goals': goals.filter(is_completed=False)[:3],
            'recent_transactions': transactions[:7],
            'notifications': notifications,
            'wallets': wallets,
            'transaction_count': transactions.count(),
        }
        cache.set(cache_key, data, 300)
    
    return render(request, 'dashboard.html', data)

@login_required
def add_transaction(request):
    if request.method == 'POST':
        form = TransactionForm(request.POST, user=request.user)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            transaction.save()
            
            # Clear cache
            cache.delete(f'dashboard_{request.user.id}')
            
            messages.success(request, '✅ Transaction added!')
            return redirect('dashboard')
    else:
        form = TransactionForm(user=request.user)
    return render(request, 'add_transaction.html', {'form': form})

@login_required
def edit_transaction(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk, user=request.user)
    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=transaction, user=request.user)
        if form.is_valid():
            form.save()
            cache.delete(f'dashboard_{request.user.id}')
            messages.success(request, '✏️ Transaction updated!')
            return redirect('transaction_list')
    else:
        form = TransactionForm(instance=transaction, user=request.user)
    return render(request, 'edit_transaction.html', {'form': form, 'transaction': transaction})

@login_required
def delete_transaction(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk, user=request.user)
    if request.method == 'POST':
        transaction.delete()
        cache.delete(f'dashboard_{request.user.id}')
        messages.success(request, '🗑️ Transaction deleted!')
        return redirect('transaction_list')
    return render(request, 'confirm_delete.html', {'transaction': transaction})

@login_required
def transaction_list(request):
    transactions = Transaction.objects.filter(user=request.user)
    
    filter_type = request.GET.get('type')
    if filter_type and filter_type != 'all':
        transactions = transactions.filter(type=filter_type)
    
    period = request.GET.get('period')
    if period == 'week':
        transactions = transactions.filter(date__gte=timezone.now().date() - timedelta(days=7))
    elif period == 'month':
        transactions = transactions.filter(date__gte=timezone.now().date() - timedelta(days=30))
    
    search = request.GET.get('search')
    if search:
        transactions = transactions.filter(Q(description__icontains=search) | Q(category__name__icontains=search))
    
    total_income = transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or 0
    total_expenses = transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or 0
    
    context = {
        'transactions': transactions,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'balance': total_income - total_expenses,
        'filter_type': filter_type,
        'period': period,
        'search': search,
    }
    return render(request, 'transaction_list.html', context)

@login_required
def budgets(request):
    current_month = timezone.now().month
    current_year = timezone.now().year
    
    if request.method == 'POST':
        form = BudgetForm(request.POST, user=request.user)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.user = request.user
            budget.save()
            cache.delete(f'dashboard_{request.user.id}')
            messages.success(request, '💰 Budget created!')
            return redirect('budgets')
    else:
        form = BudgetForm(user=request.user)
    
    budgets = Budget.objects.filter(user=request.user, month=current_month, year=current_year)
    budget_data = []
    for budget in budgets:
        spent = budget.spent_amount()
        status = budget.get_alert_status()
        budget_data.append({
            'budget': budget,
            'spent': spent,
            'remaining': budget.amount - spent,
            'progress': budget.progress(),
            'alert_status': status[0],
            'alert_message': status[1],
            'alert_text': status[2],
        })
    
    month_names = {
        1: 'January', 2: 'February', 3: 'March', 4: 'April',
        5: 'May', 6: 'June', 7: 'July', 8: 'August',
        9: 'September', 10: 'October', 11: 'November', 12: 'December'
    }
    
    context = {
        'form': form,
        'budgets': budget_data,
        'total_budgeted': budgets.aggregate(Sum('amount'))['amount__sum'] or 0,
        'current_month': current_month,
        'current_year': current_year,
        'current_month_name': month_names.get(current_month, ''),
    }
    return render(request, 'budgets.html', context)

@login_required
def savings_goals(request):
    if request.method == 'POST':
        form = SavingsGoalForm(request.POST)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            goal.save()
            messages.success(request, '🎯 Goal created!')
            return redirect('savings_goals')
    else:
        form = SavingsGoalForm()
    
    goals = SavingsGoal.objects.filter(user=request.user)
    context = {
        'form': form,
        'goals': goals,
        'total_target': goals.aggregate(Sum('target_amount'))['target_amount__sum'] or 0,
        'total_saved': goals.aggregate(Sum('current_amount'))['current_amount__sum'] or 0,
    }
    return render(request, 'goals.html', context)

@login_required
def accounts_view(request):
    if request.method == 'POST':
        form = AccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.user = request.user
            account.save()
            cache.delete(f'dashboard_{request.user.id}')
            messages.success(request, '🏦 Account added!')
            return redirect('accounts')
    else:
        form = AccountForm()
    
    accounts = Account.objects.filter(user=request.user)
    context = {
        'form': form,
        'accounts': accounts,
        'total_balance': accounts.aggregate(Sum('balance'))['balance__sum'] or 0,
    }
    return render(request, 'accounts.html', context)

@login_required
def wallets_view(request):
    if request.method == 'POST':
        form = WalletForm(request.POST)
        if form.is_valid():
            wallet = form.save(commit=False)
            wallet.user = request.user
            if wallet.is_primary:
                Wallet.objects.filter(user=request.user, is_primary=True).update(is_primary=False)
            wallet.save()
            messages.success(request, '💰 Wallet created!')
            return redirect('wallets')
    else:
        form = WalletForm()
    
    wallets = Wallet.objects.filter(user=request.user)
    context = {
        'form': form,
        'wallets': wallets,
        'total_balance': wallets.aggregate(Sum('balance'))['balance__sum'] or 0,
    }
    return render(request, 'wallets.html', context)

@login_required
def recurring_transactions(request):
    if request.method == 'POST':
        form = RecurringTransactionForm(request.POST, user=request.user)
        if form.is_valid():
            recurring = form.save(commit=False)
            recurring.user = request.user
            recurring.save()
            messages.success(request, '🔄 Recurring added!')
            return redirect('recurring')
    else:
        form = RecurringTransactionForm(user=request.user)
    
    recurring = RecurringTransaction.objects.filter(user=request.user, is_active=True)
    context = {
        'form': form,
        'recurring': recurring,
        'total_monthly': recurring.filter(frequency='monthly').aggregate(Sum('amount'))['amount__sum'] or 0,
    }
    return render(request, 'recurring.html', context)

@login_required
def reports(request):
    transactions = Transaction.objects.filter(user=request.user)
    total_income = transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or 0
    total_expenses = transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Spending patterns
    top_categories = transactions.filter(type='expense').values('category__name').annotate(
        total=Sum('amount')
    ).order_by('-total')[:5]
    
    context = {
        'total_income': total_income,
        'total_expenses': total_expenses,
        'balance': total_income - total_expenses,
        'transaction_count': transactions.count(),
        'top_categories': top_categories,
    }
    return render(request, 'reports.html', context)

@login_required
def export_csv(request):
    transactions = Transaction.objects.filter(user=request.user)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="transactions.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Category', 'Type', 'Description', 'Amount', 'Payment Method'])
    
    for t in transactions:
        writer.writerow([
            t.date.strftime('%Y-%m-%d'),
            t.category.name if t.category else 'Uncategorized',
            t.get_type_display(),
            t.description or '',
            float(t.amount),
            t.get_payment_method_display()
        ])
    
    return response

@login_required
def generate_pdf_report(request):
    """Generate PDF expense report"""
    transactions = Transaction.objects.filter(user=request.user, type='expense')
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    story.append(Paragraph(f"MoneyMuse - Expense Report", styles['Title']))
    story.append(Paragraph(f"User: {request.user.username}", styles['Normal']))
    story.append(Paragraph(f"Date: {datetime.now().strftime('%B %d, %Y')}", styles['Normal']))
    story.append(Spacer(1, 12))
    
    # Summary
    total = transactions.aggregate(Sum('amount'))['amount__sum'] or 0
    count = transactions.count()
    story.append(Paragraph(f"Total Expenses: ${total:.2f}", styles['Heading2']))
    story.append(Paragraph(f"Number of Transactions: {count}", styles['Normal']))
    story.append(Spacer(1, 12))
    
    # Table
    data = [['Date', 'Category', 'Description', 'Amount']]
    for t in transactions[:30]:
        data.append([
            t.date.strftime('%Y-%m-%d'),
            t.category.name if t.category else 'Uncategorized',
            t.description or '-',
            f'${t.amount:.2f}'
        ])
    
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    story.append(table)
    doc.build(story)
    
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename='expense_report.pdf')

@login_required
def currency_converter(request):
    """Convert currency using external API"""
    if request.method == 'POST':
        amount = request.POST.get('amount')
        from_currency = request.POST.get('from_currency', 'USD')
        to_currency = request.POST.get('to_currency', 'EUR')
        
        try:
            url = f'https://api.exchangerate-api.com/v4/latest/{from_currency}'
            response = requests.get(url, timeout=5)
            data = response.json()
            rate = data['rates'].get(to_currency, 1)
            converted = float(amount) * rate
            return JsonResponse({
                'success': True,
                'converted': round(converted, 2),
                'rate': round(rate, 4)
            })
        except:
            return JsonResponse({'success': False, 'error': 'API error'})
    
    return render(request, 'currency_converter.html')

@login_required
def spending_patterns(request):
    user = request.user
    transactions = Transaction.objects.filter(user=user)
    
    # Most expensive month
    monthly = transactions.annotate(month=TruncMonth('date')).values('month').annotate(
        total=Sum('amount')
    ).order_by('-total')[:6]
    
    # Top category
    top_category = transactions.filter(type='expense').values('category__name').annotate(
        total=Sum('amount')
    ).order_by('-total').first()
    
    # Average spending
    avg_spending = transactions.filter(type='expense').aggregate(Avg('amount'))['amount__avg'] or 0
    
    # Daily average
    if transactions.count() > 0:
        first_date = transactions.last().date
        days = (timezone.now().date() - first_date).days or 1
        daily_avg = (transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or 0) / days
    else:
        daily_avg = 0
    
    context = {
        'monthly': monthly,
        'top_category': top_category,
        'avg_spending': avg_spending,
        'daily_avg': daily_avg,
        'transaction_count': transactions.count(),
    }
    return render(request, 'patterns.html', context)

@login_required
def budget_suggestions(request):
    user = request.user
    transactions = Transaction.objects.filter(user=user)
    
    suggestions = []
    top_categories = transactions.filter(type='expense').values('category__name').annotate(
        total=Sum('amount')
    ).order_by('-total')[:5]
    
    for cat in top_categories:
        suggestions.append({
            'category': cat['category__name'],
            'suggested_budget': round(float(cat['total']) * 0.8, 2),
            'current': round(float(cat['total']), 2),
        })
    
    return JsonResponse({'suggestions': suggestions})