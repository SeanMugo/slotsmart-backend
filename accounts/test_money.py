from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from decimal import Decimal
from .models import User


class AddTestMoneyView(APIView):
    """
    POST /api/auth/add-test-money/
    Add test money to driver's wallet
    Only drivers can use this
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        
        # Only drivers can have wallets
        if user.role != 'driver':
            return Response({
                'success': False,
                'error': 'Only drivers can have wallet balance'
            }, status=403)
        
        # Get amount from request (default 1000.00)
        amount = Decimal(request.data.get('amount', 1000.00))
        
        if amount <= 0:
            return Response({
                'success': False,
                'error': 'Amount must be greater than 0'
            }, status=400)
        
        user.wallet_balance = (user.wallet_balance or 0) + amount
        user.save()
        
        return Response({
            'success': True,
            'message': f'Added {amount} test money to your wallet',
            'data': {
                'new_balance': str(user.wallet_balance),
                'amount_added': str(amount)
            }
        })