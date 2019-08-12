from django.db import models


class Source(models.Model):
    name = models.CharField(max_length=20)

    def __str__(self):
        return self.name


class Inflection(models.Model):
    context = models.CharField(max_length=40)
    analysis = models.CharField(max_length=50, default="")
    is_lemma = models.BooleanField(default=False)
    as_is = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["context"])]

    def __str__(self):
        return self.context


class Definition(models.Model):
    context = models.CharField(max_length=200)
    sources = models.ManyToManyField(Source)

    lemma = models.ForeignKey(Inflection, on_delete=models.CASCADE, default="")

    def __str__(self):
        return self.context
