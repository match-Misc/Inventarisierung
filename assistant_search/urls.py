from django.urls import path

from . import views

app_name = "assistant_search"

urlpatterns = [
    path("", views.chat, name="chat"),
    path("nachricht/", views.message, name="message"),
    path("pruefliste/", views.proposal_list, name="proposals"),
    path("pruefliste/<int:pk>/", views.review_proposal, name="review"),
]
