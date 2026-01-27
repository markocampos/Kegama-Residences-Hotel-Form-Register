from django.db import models
import uuid

class Employee(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    position = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, default='ACTIVE', choices=[('ACTIVE', 'Active'), ('INACTIVE', 'Inactive')])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta:
        ordering = ['last_name', 'first_name']

class Payslip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payslips')
    pay_period = models.CharField(max_length=50)
    pay_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    # Earnings
    earning_regular = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    earning_holiday = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    earning_overtime = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    earning_allowances = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    earning_13th = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    earning_other = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Deductions
    deduction_sss = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deduction_philhealth = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deduction_pagibig = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deduction_tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deduction_cashadv = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deduction_other = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    @property
    def total_earnings(self):
        return (self.earning_regular + self.earning_holiday + self.earning_overtime + 
                self.earning_allowances + self.earning_13th + self.earning_other)

    @property
    def total_deductions(self):
        return (self.deduction_sss + self.deduction_philhealth + self.deduction_pagibig + 
                self.deduction_tax + self.deduction_cashadv + self.deduction_other)

    @property
    def net_pay(self):
        return self.total_earnings - self.total_deductions

    class Meta:
        ordering = ['-pay_date', 'employee__last_name']
