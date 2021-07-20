# Motivation / Rationale

Django comes with a [basic permissions system](https://docs.djangoproject.com/en/dev/topics/auth/default/#permissions-and-authorization)
  however the bundled `ModelBackend` suffers from the following limitations:

* **No support for object-based permissions**. While django's abstract permissions system supports an
    `obj` argument, the `ModelBackend` will treat anything with `obj != None` as permission denied.

* **`ModelBackend` assumes that every permission is attached to a model**. This is not always the case
    (eg consider a site-wide report).
    If you attempt to create permissions that aren't attached to an existing model then on the next migration it will
    prompt you to delete the permissions. That can lead to bad outcomes for inexperienced developers!
  
* **Simplistic**. A user/group either has a permission or doesn't.
    There is no way to define logic associated with a permission
    (eg "user has permission X only if their account is more than 1 month old")
    and this often means developers put such logic in the views. 
    * [`django-rules`](https://github.com/dfunckt/django-rules) significantly improves the power of the django
      permissions system by allowing for permissions to be based on execution of code
      
* **No versioning**. By default, making changes to permissions leaves no audit trail.

* **Permission names**. Django permission names are in the form `f'{app_label}.{action}_{model}'`.
    This does not sort well.

Default django permissions has the following tradeoffs: 

* **Enumerating permssions**:
    The permissions attached to a user (or users that have a given permission) can be trivially enumerated with
    a single query. While django doesn't provide a view for this it is simple to make.
  
    * Note that while `django-rules` makes permissions much more powerful it also removes the ability to enumerate
        permissions. 

* **Permissions can attach to a user**:
    A single user can have a custom permission attached rather than being limited to inheriting them from their Group.
    This is flexible, but it also opens up the possibilty of unexpected permission interactions.
    For example, an inexperienced admin may attach the "Edit Foo" permission to a user which may cause problems if
    the developer expects that an "Edit Foo" users also has the "View Foo" permission.  
  
* **Can be edited by end users**: End users can modify permissions. This is flexible but (as above) permission
    interactions can be complicated and in practice this is usually best left to BAs or Developers.
  
# Design Decisions

* The permission system is not data, it is code and should be treated like code.
    * Permission versioning is present via source control (git or similar).
    
* Permissions are stored in CSV file(s).
    * This means that the permissions file(s) can be shared with non-technical users.
      but only people with source write access can commit changes.

* Permissions can only be granted to a user type, not to individual users.
    * This makes it possible to analyse permission interactions as there is a limited number of user types. 
   
* Permissions do not need to be attached to a model.
  
* Permissions are explicitly labelled as global or per-object.

* Relationship with `django-rules`:
    * `django-rules` is unopionated and imposes so little structure that by itself it is difficult to have an
        overview of what permissions are available to users.
    * `django-rules` is excellent for complicated permissions logic.
        For more complicated rules, we will leverage `django-rules` functionality.

* Different permissions systems should 'play nicely' together.
    * This allows incremental migration between systems. 