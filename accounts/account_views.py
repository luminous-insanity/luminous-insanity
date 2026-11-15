"""Website page for deleting your own account (also the public deletion URL
that Google Play asks for). Mobile uses POST /api/v1/me/delete/."""
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .account_deletion import delete_account


@login_required
def delete_account_page(request):
    if request.method == 'POST':
        user = request.user
        confirm = (request.POST.get('confirm') or '').strip().upper()
        error = None
        if confirm != 'DELETE':
            error = 'Type DELETE to confirm.'
        elif user.has_usable_password() and not user.check_password(request.POST.get('password') or ''):
            error = 'That password is not correct.'
        if error:
            messages.error(request, error)
            return render(request, 'accounts/delete_account.html', {
                'needs_password': user.has_usable_password(),
            })
        delete_account(user)
        logout(request)
        messages.success(request, 'Your account has been deleted.')
        return redirect('home')
    return render(request, 'accounts/delete_account.html', {
        'needs_password': request.user.has_usable_password(),
    })
