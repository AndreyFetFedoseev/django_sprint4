from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.contrib.auth.views import LoginView
from django.db.models import Count
from django.contrib.auth import get_user_model
from django.http import Http404

from .models import Category, Post, Comment
from .forms import PostForm, CommentForm, ProfileForm, CustomUserCreationForm
from .decorators import check_post_access

User = get_user_model()


def paginate_queryset(request, queryset, per_page=10):
    """Пагинация запроса и возвращение объекта страницы."""
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return page_obj


def optimize_posts(queryset):
    return queryset.select_related('author', 'category', 'location').filter(
        is_published=True,
        pub_date__lte=timezone.now(),
        category__is_published=True
    )


def index(request):
    posts = optimize_posts(Post.objects.all()).annotate(
        comment_count=Count('comments')
    ).order_by('-pub_date')
    page_obj = paginate_queryset(request, posts)

    context = {'page_obj': page_obj}
    return render(request, 'blog/index.html', context)


def category_posts(request, category_slug):
    category = get_object_or_404(Category,
                                 slug=category_slug, is_published=True)
    posts = optimize_posts(Post.objects.filter(category=category)).annotate(
        comment_count=Count('comments')
    ).order_by('-pub_date')
    page_obj = paginate_queryset(request, posts)

    context = {'category': category, 'page_obj': page_obj}
    return render(request, 'blog/category.html', context)


@login_required
@check_post_access
def post_detail(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    comments = post.comments.filter(is_published=True).order_by('created_at')
    form = CommentForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.author = request.user
        comment.save()
        return redirect('blog:post_detail', post_id=post.id)

    context = {
        'post': post,
        'comments': comments,
        'form': form
    }
    return render(request, 'blog/detail.html', context)


class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'registration/registration_form.html'


class ProfileView(DetailView):
    model = User
    template_name = 'profile.html'
    context_object_name = 'user_profile'
    slug_field = 'username'
    slug_url_kwarg = 'username'

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


@login_required
def create_post(request):
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            if not post.pub_date:
                post.pub_date = timezone.now()
            post.save()
            return redirect('blog:profile', username=request.user.username)
    else:
        form = PostForm()
    return render(request, 'blog/create.html', {'form': form})


@login_required
def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if request.user != post.author:
        return redirect('blog:post_detail', post_id=post.id)

    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            return redirect('blog:post_detail', post_id=post.id)
    else:
        form = PostForm(instance=post)
    return render(request, 'blog/create.html', {'form': form, 'is_edit': True})


@login_required
def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if request.user != post.author:
        raise Http404

    if request.method == 'POST':
        post.delete()
        return redirect('blog:profile', username=request.user.username)

    context = {'object': post, 'is_delete': True, 'delete_type': 'post'}
    return render(request, 'blog/create.html', context)


@login_required
def edit_profile(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect('blog:profile', username=request.user.username)
    else:
        form = ProfileForm(instance=request.user)
    return render(request, 'blog/user.html', {'form': form})


def profile(request, username):
    user_profile = get_object_or_404(User, username=username)
    posts = Post.objects.filter(author=user_profile).annotate(
        comment_count=Count('comments')
    ).order_by('-pub_date')

    if not request.user.is_authenticated or request.user != user_profile:
        posts = posts.filter(is_published=True, pub_date__lte=timezone.now())

    page_obj = paginate_queryset(request, posts)

    context = {'profile': user_profile, 'page_obj': page_obj}
    return render(request, 'blog/profile.html', context)


class CustomLoginView(LoginView):
    template_name = 'registration/login.html'

    def get_success_url(self):
        username = self.request.user.username
        return reverse_lazy('blog:profile', kwargs={'username': username})


@login_required
@require_POST
def add_comment(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.author = request.user
        comment.post = post
        comment.save()
    return redirect('blog:post_detail', post_id=post.id)


@login_required
def edit_comment(request, post_id, comment_id):
    post = get_object_or_404(Post, id=post_id)
    comment = get_object_or_404(Comment, id=comment_id, post=post)
    if request.user != comment.author:
        return redirect('blog:post_detail', post_id=post.id)

    if request.method == 'POST':
        form = CommentForm(request.POST, instance=comment)
        if form.is_valid():
            form.save()
            return redirect('blog:post_detail', post_id=post.id)
    else:
        form = CommentForm(instance=comment)
    return render(request, 'blog/create.html', {'form': form, 'is_edit': True})


@login_required
def delete_comment(request, post_id, comment_id):
    post = get_object_or_404(Post, id=post_id)
    comment = get_object_or_404(Comment, id=comment_id, post=post)
    if request.user != comment.author:
        raise Http404

    if request.method == 'POST':
        comment.delete()
        return redirect('blog:post_detail', post_id=post.id)

    context = {'object': comment, 'is_delete': True, 'delete_type': 'comment'}
    return render(request, 'blog/create.html', context)
