from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal

class Account(models.Model):
    ACCOUNT_TYPES = [
        ('checking', 'Checking Account'),
        ('savings', 'Savings Account'),
        ('credit', 'Credit Card'),
        ('cash', 'Cash'),
        ('investment', 'Investment'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='USD')
    color = models.CharField(max_length=7, default='#007bff')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} (${self.balance})"

class Category(models.Model):
    TYPE_CHOICES = [('income', 'Income'), ('expense', 'Expense')]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    icon = models.CharField(max_length=50, default='fa-tag')
    color = models.CharField(max_length=7, default='#6c757d')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.icon} {self.name}"
    
    class Meta:
        verbose_name_plural = "Categories"

class Transaction(models.Model):
    TYPE_CHOICES = [('income', 'Income'), ('expense', 'Expense')]
    PAYMENT_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('bank', 'Bank Transfer'),
        ('upi', 'UPI'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default='cash')
    date = models.DateField(default=timezone.now)
    receipt = models.ImageField(upload_to='receipts/', null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.type}: ${self.amount} - {self.description}"
    
    class Meta:
        ordering = ['-date']

class Budget(models.Model):
    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    month = models.IntegerField(choices=MONTH_CHOICES, default=timezone.now().month)
    year = models.IntegerField(default=timezone.now().year)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['user', 'category', 'month', 'year']
    
    def spent_amount(self):
        start = timezone.datetime(self.year, self.month, 1)
        if self.month == 12:
            end = timezone.datetime(self.year + 1, 1, 1)
        else:
            end = timezone.datetime(self.year, self.month + 1, 1)
        
        return Transaction.objects.filter(
            user=self.user,
            category=self.category,
            type='expense',
            date__gte=start,
            date__lt=end
        ).aggregate(models.Sum('amount'))['amount__sum'] or Decimal('0.00')
    
    def progress(self):
        if self.amount > 0:
            return min((self.spent_amount() / self.amount) * 100, 100)
        return 0
    
    def get_alert_status(self):
        progress = self.progress()
        if progress >= 100:
            return 'danger', '⚠️ Exceeded!', 'You have exceeded this budget!'
        elif progress >= 80:
            return 'warning', '🔔 Almost Exceeded!', f'You have used {progress:.1f}% of your budget!'
        return 'success', '✅ On Track', f'You have used {progress:.1f}% of your budget'

class SavingsGoal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deadline = models.DateField()
    icon = models.CharField(max_length=50, default='🎯')
    color = models.CharField(max_length=7, default='#28a745')
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def progress(self):
        if self.target_amount > 0:
            return min((self.current_amount / self.target_amount) * 100, 100)
        return 0
    
    def days_left(self):
        days = (self.deadline - timezone.now().date()).days
        return max(0, days)

class RecurringTransaction(models.Model):
    FREQUENCY = [('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly'), ('yearly', 'Yearly')]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    frequency = models.CharField(max_length=10, choices=FREQUENCY)
    next_due_date = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    type = models.CharField(max_length=50, default='info')
    link = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']

class Wallet(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='USD')
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} (${self.balance})"

class Card(models.Model):
    CARD_TYPES = [('debit', 'Debit'), ('credit', 'Credit')]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE)
    type = models.CharField(max_length=10, choices=CARD_TYPES)
    last_four = models.CharField(max_length=4)
    expiry_date = models.DateField()
    is_active = models.BooleanField(default=True)
    limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.type} card ending in {self.last_four}"

class ExpenseSplit(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='splits')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} owes ${self.amount}"