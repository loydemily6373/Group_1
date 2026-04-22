from sellers.views import *

def create_product(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user
            product.save()
            return redirect('product_list')
    else:
        form = ProductForm(request.POST or None, request.FILES or None, instance=product)
        
    return render(request, 'products/create_product.html', {'form': form})
